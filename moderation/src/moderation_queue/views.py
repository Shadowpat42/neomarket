from __future__ import annotations

import json
import os
from urllib import request as urlrequest

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import b2b_client
from .models import BlockingReason, Ticket, TicketFieldReport, TicketStatus
from .serializers import TicketResponseSerializer


# ── B2B helper (module-level so tests can patch it) ───────────────────────────

def _fetch_sku_count(product_id: str) -> int | None:
    """
    Returns the number of SKUs for a product fetched from B2B.
    Returns None on any network / parse error (best-effort; approval not blocked).
    """
    b2b_url = os.getenv("B2B_URL", "http://b2b:8001").rstrip("/")
    mod_key = os.getenv("MOD_TO_B2B_KEY", "mod_to_b2b_key")
    endpoint = f"{b2b_url}/api/v1/products/{product_id}"
    req = urlrequest.Request(
        endpoint,
        method="GET",
        headers={"X-Service-Key": mod_key},
    )
    try:
        with urlrequest.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return len(data.get("skus", []))
    except Exception:
        return None


# ── Shared guard ──────────────────────────────────────────────────────────────

def _terminal_response():
    """Return 403 for any attempt to mutate a HARD_BLOCKED ticket."""
    return Response(
        {
            "code": "TICKET_TERMINAL",
            "message": "Ticket is permanently blocked and cannot be modified",
        },
        status=status.HTTP_403_FORBIDDEN,
    )


# ── Skeleton view kept for backwards-compat ───────────────────────────────────

class GetNextProductView(APIView):
    def post(self, request):
        return Response({"message": "Get next product for moderation skeleton"})


# ── US-MOD-03: Approve ticket ─────────────────────────────────────────────────

class TicketApproveView(APIView):
    """
    POST /api/v1/tickets/{ticket_id}/approve

    Approves a moderation ticket:
      1. Ticket must be IN_REVIEW and assigned to the calling moderator.
      2. Product must have at least one SKU (checked via B2B).
      3. Updates ticket to APPROVED, sends MODERATED event to B2B.
      4. If B2B call fails → rolls back ticket to IN_REVIEW and returns 500.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):
        # ── 1. Fetch ticket ───────────────────────────────────────────────────
        try:
            ticket = Ticket.objects.get(pk=ticket_id)
        except (Ticket.DoesNotExist, Exception):
            return Response(
                {"code": "NOT_FOUND", "message": "Ticket not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ── 2. Terminal guard (US-MOD-05) ─────────────────────────────────────
        if ticket.is_terminal():
            return _terminal_response()

        # ── 3. Status check ───────────────────────────────────────────────────
        if ticket.status != TicketStatus.IN_REVIEW:
            return Response(
                {
                    "code": "TICKET_WRONG_STATUS",
                    "message": "Product is not in review status",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # ── 4. Ownership check ────────────────────────────────────────────────
        if ticket.assigned_moderator_id != request.user.pk:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "This moderation card is not assigned to you",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ── 5. SKU presence check (via B2B) ───────────────────────────────────
        sku_count = _fetch_sku_count(str(ticket.product_id))
        if sku_count is not None and sku_count == 0:
            return Response(
                {
                    "code": "NO_SKUS",
                    "message": "Product has no SKUs, cannot approve",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # ── 6. Apply decision ─────────────────────────────────────────────────
        comment = request.data.get("comment") if request.data else None
        ticket.status = TicketStatus.APPROVED
        ticket.decision_at = timezone.now()
        ticket.decision_comment = comment
        ticket.save(update_fields=["status", "decision_at", "decision_comment", "updated_at"])

        # ── 7. Notify B2B ─────────────────────────────────────────────────────
        try:
            b2b_client.send_moderated_event(
                product_id=ticket.product_id,
                idempotency_key=ticket.id,
                moderator_comment=comment,
            )
        except Exception:
            ticket.status = TicketStatus.IN_REVIEW
            ticket.decision_at = None
            ticket.decision_comment = None
            ticket.save(update_fields=["status", "decision_at", "decision_comment", "updated_at"])
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "Failed to notify B2B; please retry"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(TicketResponseSerializer(ticket).data, status=status.HTTP_200_OK)


# ── US-MOD-05: Block ticket (soft or hard) ────────────────────────────────────

class TicketBlockView(APIView):
    """
    POST /api/v1/tickets/{ticket_id}/block

    Blocks a product from the catalog. The type of block is determined by the
    BlockingReason.hard_block flag:
      hard_block=False → BLOCKED  (seller can correct and resubmit)
      hard_block=True  → HARD_BLOCKED (terminal — no further seller action possible)

    On success, sends a BLOCKED event to B2B.
    If B2B call fails, rolls back the ticket to IN_REVIEW.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):
        # ── 1. Fetch ticket ───────────────────────────────────────────────────
        try:
            ticket = Ticket.objects.get(pk=ticket_id)
        except (Ticket.DoesNotExist, Exception):
            return Response(
                {"code": "NOT_FOUND", "message": "Ticket not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ── 2. Terminal guard ─────────────────────────────────────────────────
        if ticket.is_terminal():
            return _terminal_response()

        # ── 3. Status check ───────────────────────────────────────────────────
        if ticket.status != TicketStatus.IN_REVIEW:
            return Response(
                {
                    "code": "TICKET_WRONG_STATUS",
                    "message": "Ticket is not in review",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # ── 4. Ownership check ────────────────────────────────────────────────
        if ticket.assigned_moderator_id != request.user.pk:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "This ticket is not assigned to you",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ── 5. Validate blocking reasons ──────────────────────────────────────
        reason_ids = request.data.get("blocking_reason_ids", [])
        if not reason_ids:
            return Response(
                {"code": "INVALID_REQUEST", "message": "blocking_reason_ids is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reasons = list(
            BlockingReason.objects.filter(id__in=reason_ids, is_active=True)
        )
        if len(reasons) != len(reason_ids):
            return Response(
                {"code": "NOT_FOUND", "message": "One or more blocking reasons not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_hard = any(r.hard_block for r in reasons)
        new_status = TicketStatus.HARD_BLOCKED if is_hard else TicketStatus.BLOCKED
        comment = request.data.get("comment")
        field_reports_data = request.data.get("field_reports", [])
        primary_reason = reasons[0]

        # ── 6. Apply decision ─────────────────────────────────────────────────
        ticket.status = new_status
        ticket.decision_at = timezone.now()
        ticket.decision_comment = comment
        ticket.blocking_reason = primary_reason
        ticket.save(
            update_fields=[
                "status", "decision_at", "decision_comment",
                "blocking_reason", "updated_at",
            ]
        )

        # Replace field reports
        ticket.field_reports.all().delete()
        for fr in field_reports_data:
            TicketFieldReport.objects.create(
                ticket=ticket,
                field_path=fr.get("field_path", ""),
                message=fr.get("message", ""),
                severity=fr.get("severity", "ERROR"),
            )

        # ── 7. Notify B2B ─────────────────────────────────────────────────────
        try:
            b2b_client.send_blocked_event(
                product_id=ticket.product_id,
                idempotency_key=ticket.id,
                hard_block=is_hard,
                blocking_reason=primary_reason,
                comment=comment,
                field_reports=field_reports_data,
            )
        except Exception:
            # Roll back — moderator can retry
            ticket.status = TicketStatus.IN_REVIEW
            ticket.decision_at = None
            ticket.decision_comment = None
            ticket.blocking_reason = None
            ticket.save(
                update_fields=[
                    "status", "decision_at", "decision_comment",
                    "blocking_reason", "updated_at",
                ]
            )
            ticket.field_reports.all().delete()
            return Response(
                {
                    "code": "B2B_UNAVAILABLE",
                    "message": "Failed to notify B2B; please retry",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(TicketResponseSerializer(ticket).data, status=status.HTTP_200_OK)


# ── Incoming B2B events ───────────────────────────────────────────────────────

class B2BEventView(APIView):
    """
    POST /api/v1/b2b/events

    Receives product lifecycle events from B2B:
      PRODUCT_CREATED  — create a new moderation ticket (PENDING)
      PRODUCT_EDITED   — create an EDIT ticket, unless the product is HARD_BLOCKED
                         (HARD_BLOCKED is terminal → event is silently acknowledged)
      PRODUCT_DELETED  — remove all moderation records for the product

    Auth: X-Service-Key header checked against settings.B2B_TO_MOD_KEY.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # ── Service-key auth ──────────────────────────────────────────────────
        incoming_key = request.headers.get("X-Service-Key", "")
        expected_key = getattr(settings, "B2B_TO_MOD_KEY", "b2b_to_mod_key")
        if incoming_key != expected_key:
            return Response(
                {"code": "UNAUTHORIZED", "message": "Invalid service key"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        event_type = request.data.get("event_type")
        payload = request.data.get("payload", {})
        product_id = payload.get("product_id") if payload else None

        if not product_id:
            return Response(
                {"code": "INVALID_REQUEST", "message": "payload.product_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── PRODUCT_DELETED: purge all ticket records ──────────────────────────
        if event_type == "PRODUCT_DELETED":
            Ticket.objects.filter(product_id=product_id).delete()
            return Response(status=status.HTTP_202_ACCEPTED)

        # ── PRODUCT_EDITED: skip if HARD_BLOCKED (terminal) ───────────────────
        if event_type == "PRODUCT_EDITED":
            if Ticket.objects.filter(
                product_id=product_id, status=TicketStatus.HARD_BLOCKED
            ).exists():
                # Terminal status — seller edits are legally/commercially irrelevant.
                return Response(status=status.HTTP_202_ACCEPTED)
            # Out of scope for US-MOD-05; create EDIT ticket in a future US.
            return Response(status=status.HTTP_202_ACCEPTED)

        # ── PRODUCT_CREATED: out of scope for US-MOD-05 ───────────────────────
        if event_type == "PRODUCT_CREATED":
            return Response(status=status.HTTP_202_ACCEPTED)

        return Response(
            {"code": "UNKNOWN_EVENT", "message": f"Unknown event_type: {event_type}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
