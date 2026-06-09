"""
US-MOD-05 tests: Hard block (POST /api/v1/tickets/{ticket_id}/block)

Covered scenarios:
  hard_block_transitions_to_terminal_and_emits_event  — happy path
  hard_block_event_carries_hard_block_true             — flag in B2B event
  any_modify_on_hard_blocked_returns_403               — terminal guard
  edited_event_on_hard_blocked_is_ignored              — B2B EDITED idempotent
  deleted_event_removes_hard_blocked                   — B2B DELETED cleans up

ADR – Guaranteeing irreversibility of HARD_BLOCKED
===================================================
Alternatives considered:
  A. Separate archive table — moves HARD_BLOCKED rows to a "terminal" table.
     Pros: physically impossible to cycle back via normal ORM path.
     Cons: complex join queries, harder to audit in one place, expensive data migration.
  B. is_terminal boolean flag — orthogonal flag checked alongside status.
     Pros: simple schema. Cons: two fields can diverge (flag=True but status != HARD_BLOCKED),
     creating silent bugs; every new endpoint must remember to check both.
  C. Terminal enum status + guard on every mutating endpoint (chosen).
     pros: single source of truth (status column), easy audit (search for HARD_BLOCKED in
     query logs), Django Admin still lets a super-admin update the field directly for
     emergencies while the audit log captures the change. cons: each new endpoint must
     call is_terminal() — mitigated by shared _terminal_response() helper.

Decision: option C. Criteria used:
  1. Risk of accidental bypass — requires intentionally skipping a single guard function.
  2. Audit clarity — one column, clear history in change logs, trivially queryable.
"""

import uuid
from unittest.mock import call, patch

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import BlockingReason, Ticket, TicketKind, TicketStatus

B2B_EVENTS_URL = "/api/v1/b2b/events"
SVC_HEADERS = {"HTTP_X_SERVICE_KEY": "b2b_to_mod_key"}


def _block_url(ticket_id):
    return f"/api/v1/tickets/{ticket_id}/block"


def _approve_url(ticket_id):
    return f"/api/v1/tickets/{ticket_id}/approve"


def _make_moderator(username: str) -> User:
    return User.objects.create_user(username=username, password="testpass123!")


def _make_hard_reason() -> BlockingReason:
    return BlockingReason.objects.create(
        code="COUNTERFEIT_GOODS",
        title="Контрафактный товар",
        hard_block=True,
    )


def _make_soft_reason() -> BlockingReason:
    return BlockingReason.objects.create(
        code="BAD_IMAGES",
        title="Некачественные фото",
        hard_block=False,
    )


def _make_ticket(moderator: User, ticket_status: str = TicketStatus.IN_REVIEW) -> Ticket:
    return Ticket.objects.create(
        product_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        kind=TicketKind.CREATE,
        status=ticket_status,
        assigned_moderator=moderator,
        json_after={"title": "Test product"},
    )


@override_settings(B2B_TO_MOD_KEY="b2b_to_mod_key")
class HardBlockTests(APITestCase):

    def setUp(self):
        self.moderator = _make_moderator("mod_charlie")
        self.hard_reason = _make_hard_reason()
        self.ticket = _make_ticket(self.moderator)

    # ── happy path ─────────────────────────────────────────────────────────────

    @patch("b2b_client.send_blocked_event")
    def test_hard_block_transitions_to_terminal_and_emits_event(self, mock_send):
        """
        Happy path: ticket status → HARD_BLOCKED, B2B blocking event is sent.
        The ticket is terminal after this call.
        """
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(
            _block_url(self.ticket.id),
            {
                "blocking_reason_ids": [str(self.hard_reason.id)],
                "comment": "Counterfeit confirmed",
                "field_reports": [],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], TicketStatus.HARD_BLOCKED)
        self.assertEqual(str(resp.data["product_id"]), str(self.ticket.product_id))

        # Persisted as HARD_BLOCKED
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.HARD_BLOCKED)
        self.assertTrue(self.ticket.is_terminal())
        self.assertIsNotNone(self.ticket.decision_at)

        # B2B called once
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        self.assertEqual(str(kwargs["product_id"]), str(self.ticket.product_id))

    # ── B2B event carries hard_block=True ──────────────────────────────────────

    @patch("b2b_client.send_blocked_event")
    def test_hard_block_event_carries_hard_block_true(self, mock_send):
        """
        The B2B notification must carry hard_block=True so B2B sets
        product.status = HARD_BLOCKED (not just BLOCKED).
        """
        self.client.force_authenticate(user=self.moderator)

        self.client.post(
            _block_url(self.ticket.id),
            {"blocking_reason_ids": [str(self.hard_reason.id)]},
            format="json",
        )

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        self.assertTrue(kwargs["hard_block"])
        self.assertEqual(kwargs["blocking_reason"].id, self.hard_reason.id)

    # ── terminal guard: no further mutations allowed ───────────────────────────

    @patch("b2b_client.send_blocked_event")
    @patch("moderation_queue.views._fetch_sku_count", return_value=1)
    @patch("b2b_client.send_moderated_event")
    def test_any_modify_on_hard_blocked_returns_403(
        self, mock_approve_send, mock_sku, mock_block_send
    ):
        """
        Any mutation attempt on a HARD_BLOCKED ticket must return 403.
        Tested actions: approve, block.
        """
        hard_blocked_ticket = _make_ticket(self.moderator, ticket_status=TicketStatus.HARD_BLOCKED)
        self.client.force_authenticate(user=self.moderator)

        # Attempt approve
        resp_approve = self.client.post(
            _approve_url(hard_blocked_ticket.id), format="json"
        )
        self.assertEqual(resp_approve.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp_approve.data["code"], "TICKET_TERMINAL")

        # Attempt block
        soft_reason = _make_soft_reason()
        resp_block = self.client.post(
            _block_url(hard_blocked_ticket.id),
            {"blocking_reason_ids": [str(soft_reason.id)]},
            format="json",
        )
        self.assertEqual(resp_block.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp_block.data["code"], "TICKET_TERMINAL")

        # Status must remain HARD_BLOCKED
        hard_blocked_ticket.refresh_from_db()
        self.assertEqual(hard_blocked_ticket.status, TicketStatus.HARD_BLOCKED)

        # Neither B2B client must be called
        mock_approve_send.assert_not_called()
        mock_block_send.assert_not_called()

    # ── EDITED event on HARD_BLOCKED is silently acknowledged ─────────────────

    def test_edited_event_on_hard_blocked_is_ignored(self):
        """
        When B2B sends PRODUCT_EDITED for a HARD_BLOCKED product, Moderation
        returns 202 without changing the ticket. Seller edits are irrelevant
        once a product is permanently blocked.
        """
        hard_blocked_ticket = _make_ticket(
            self.moderator, ticket_status=TicketStatus.HARD_BLOCKED
        )

        resp = self.client.post(
            B2B_EVENTS_URL,
            {
                "event_type": "PRODUCT_EDITED",
                "idempotency_key": str(uuid.uuid4()),
                "occurred_at": "2026-06-10T00:00:00.000Z",
                "payload": {
                    "product_id": str(hard_blocked_ticket.product_id),
                    "seller_id": str(uuid.uuid4()),
                    "json_before": {},
                    "json_after": {"title": "Updated title"},
                },
            },
            format="json",
            **SVC_HEADERS,
        )

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        # Ticket must remain HARD_BLOCKED — edit is a no-op
        hard_blocked_ticket.refresh_from_db()
        self.assertEqual(hard_blocked_ticket.status, TicketStatus.HARD_BLOCKED)

    # ── DELETED event removes HARD_BLOCKED ticket ─────────────────────────────

    def test_deleted_event_removes_hard_blocked(self):
        """
        When B2B sends PRODUCT_DELETED for a HARD_BLOCKED product, Moderation
        removes the ticket record. The product stays HARD_BLOCKED in B2B —
        Moderation just no longer tracks it.
        Calling DELETED twice is idempotent (second call also returns 202).
        """
        hard_blocked_ticket = _make_ticket(
            self.moderator, ticket_status=TicketStatus.HARD_BLOCKED
        )
        product_id = hard_blocked_ticket.product_id

        resp = self.client.post(
            B2B_EVENTS_URL,
            {
                "event_type": "PRODUCT_DELETED",
                "idempotency_key": str(uuid.uuid4()),
                "occurred_at": "2026-06-10T00:00:00.000Z",
                "payload": {"product_id": str(product_id)},
            },
            format="json",
            **SVC_HEADERS,
        )

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertFalse(
            Ticket.objects.filter(product_id=product_id).exists(),
            "Ticket record must be deleted from Moderation",
        )

        # Idempotent second call
        resp2 = self.client.post(
            B2B_EVENTS_URL,
            {
                "event_type": "PRODUCT_DELETED",
                "idempotency_key": str(uuid.uuid4()),
                "occurred_at": "2026-06-10T00:00:00.000Z",
                "payload": {"product_id": str(product_id)},
            },
            format="json",
            **SVC_HEADERS,
        )
        self.assertEqual(resp2.status_code, status.HTTP_202_ACCEPTED)
