from __future__ import annotations

import json
import os
from urllib import request as urlrequest

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import b2b_client
from .models import Ticket, TicketStatus
from .serializers import TicketResponseSerializer


# ── B2B helper (module-level so tests can mock it) ────────────────────────────

def _fetch_sku_count(product_id: str) -> int | None:
    """
    Returns the number of SKUs for a product fetched from B2B.
    Returns None on any network / parse error (best-effort; approval is not blocked).
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
      4. If B2B call fails → rolls back ticket status to IN_REVIEW and returns 500.
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

        # ── 2. Status check ───────────────────────────────────────────────────
        if ticket.status != TicketStatus.IN_REVIEW:
            return Response(
                {
                    "code": "TICKET_WRONG_STATUS",
                    "message": "Product is not in review status",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # ── 3. Ownership check ────────────────────────────────────────────────
        if ticket.assigned_moderator_id != request.user.pk:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "This moderation card is not assigned to you",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # ── 4. SKU presence check (via B2B) ───────────────────────────────────
        sku_count = _fetch_sku_count(str(ticket.product_id))
        if sku_count is not None and sku_count == 0:
            return Response(
                {
                    "code": "NO_SKUS",
                    "message": "Product has no SKUs, cannot approve",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # ── 5. Apply decision ─────────────────────────────────────────────────
        comment = request.data.get("comment") if request.data else None
        ticket.status = TicketStatus.APPROVED
        ticket.decision_at = timezone.now()
        ticket.decision_comment = comment
        ticket.save(update_fields=["status", "decision_at", "decision_comment", "updated_at"])

        # ── 6. Notify B2B ─────────────────────────────────────────────────────
        try:
            b2b_client.send_moderated_event(
                product_id=ticket.product_id,
                idempotency_key=ticket.id,
                moderator_comment=comment,
            )
        except Exception:
            # Roll back so the moderator can retry
            ticket.status = TicketStatus.IN_REVIEW
            ticket.decision_at = None
            ticket.decision_comment = None
            ticket.save(update_fields=["status", "decision_at", "decision_comment", "updated_at"])
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "Failed to notify B2B; please retry"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(TicketResponseSerializer(ticket).data, status=status.HTTP_200_OK)
