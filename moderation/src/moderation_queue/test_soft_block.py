"""
US-MOD-04 tests: Soft block (POST /api/v1/tickets/{ticket_id}/block)

Covered scenarios (DoD names):
  soft_block_transitions_to_blocked_with_field_reports  — happy path
  soft_block_emits_event_to_b2b                         — BLOCKED + hard_block=False
  soft_block_unknown_reason_returns_400                 — non-existent reason → 400
  soft_block_others_card_returns_403                    — wrong moderator → 403
  soft_block_invalid_field_name_returns_400             — bad field_name in reports → 400
  soft_block_hard_only_reason_routes_to_hard            — hard_block reason → HARD_BLOCKED (ADR: route)

ADR — hard_block=True reason submitted via soft-block endpoint
=============================================================
Options:
  A. Return 400 ("Use hard-block route") — forces explicit intent from UI.
     Risk: unnecessary round-trip if the UI doesn't pre-filter reasons.
  B. Silently route to HARD_BLOCKED (chosen).
     Pro: endpoint stays unified; hard_block flag on the reason is the single
     source of truth.  Con: moderator must understand that selecting a hard
     reason triggers an irreversible action.  Mitigated by having the UI
     pre-filter and warn, and by the terminal guard preventing any undo.
  C. Separate endpoint /hard-block.  Clean but duplicates auth/ownership logic.

Decision: option B (routing).  Criteria:
  1. Single endpoint → one audit log entry, simpler client code.
  2. Terminal guard in TicketBlockView/TicketApproveView prevents accidental
     undos even if the wrong status slips through.
"""

import uuid
from unittest.mock import patch

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from .models import BlockingReason, Ticket, TicketFieldReport, TicketKind, TicketStatus


def _block_url(ticket_id):
    return f"/api/v1/tickets/{ticket_id}/block"


def _make_moderator(username: str) -> User:
    return User.objects.create_user(username=username, password="testpass123!")


def _make_soft_reason() -> BlockingReason:
    return BlockingReason.objects.create(
        code="BAD_DESCRIPTION",
        title="Описание не соответствует товару",
        hard_block=False,
    )


def _make_hard_reason() -> BlockingReason:
    return BlockingReason.objects.create(
        code="COUNTERFEIT_GOODS_HARD",
        title="Контрафакт",
        hard_block=True,
    )


def _make_ticket(moderator: User, ticket_status=TicketStatus.IN_REVIEW) -> Ticket:
    return Ticket.objects.create(
        product_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        kind=TicketKind.CREATE,
        status=ticket_status,
        assigned_moderator=moderator,
        json_after={"title": "Test product"},
    )


FIELD_REPORTS = [
    {"field_name": "description", "sku_id": None, "comment": "Описание скопировано"},
    {"field_name": "product_images", "sku_id": None, "comment": "Фото размыты"},
]


class SoftBlockTests(APITestCase):

    def setUp(self):
        self.moderator = _make_moderator("mod_soft")
        self.soft_reason = _make_soft_reason()
        self.ticket = _make_ticket(self.moderator)

    # ── happy path ─────────────────────────────────────────────────────────────

    @patch("b2b_client.send_blocked_event")
    def test_soft_block_transitions_to_blocked_with_field_reports(self, mock_send):
        """
        Happy path: ticket → BLOCKED, field_reports persisted,
        B2B event sent with hard_block=False.
        """
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(
            _block_url(self.ticket.id),
            {
                "blocking_reason_ids": [str(self.soft_reason.id)],
                "comment": "Описание и фото не соответствуют товару",
                "field_reports": FIELD_REPORTS,
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], TicketStatus.BLOCKED)

        # Ticket persisted as BLOCKED
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.BLOCKED)
        self.assertFalse(self.ticket.is_terminal())
        self.assertIsNotNone(self.ticket.decision_at)
        self.assertEqual(self.ticket.blocking_reason_id, self.soft_reason.id)

        # Field reports saved correctly
        saved_reports = list(
            TicketFieldReport.objects.filter(ticket=self.ticket).values_list("field_path", flat=True)
        )
        self.assertIn("description", saved_reports)
        self.assertIn("product_images", saved_reports)

    # ── B2B event carries hard_block=False ────────────────────────────────────

    @patch("b2b_client.send_blocked_event")
    def test_soft_block_emits_event_to_b2b(self, mock_send):
        """
        The B2B notification must carry:
          hard_block=False  (reversible block)
          blocking_reason   with correct id
          field_reports     in B2B contract format {field_name, comment}
        """
        self.client.force_authenticate(user=self.moderator)

        self.client.post(
            _block_url(self.ticket.id),
            {
                "blocking_reason_ids": [str(self.soft_reason.id)],
                "comment": "Нарушения в описании",
                "field_reports": [
                    {"field_name": "description", "comment": "Описание скопировано"},
                ],
            },
            format="json",
        )

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args

        # hard_block flag
        self.assertFalse(kwargs["hard_block"])

        # product identity
        self.assertEqual(str(kwargs["product_id"]), str(self.ticket.product_id))

        # blocking_reason is passed as model instance (b2b_client extracts .id)
        self.assertEqual(kwargs["blocking_reason"].id, self.soft_reason.id)

        # field_reports normalised to {field_path, message} by views.py
        # b2b_client is responsible for converting to {field_name, comment} on the wire
        fr = kwargs["field_reports"][0]
        self.assertIn("field_path", fr)   # internal normalised key
        self.assertEqual(fr["field_path"], "description")

    # ── unhappy: non-existent blocking reason ─────────────────────────────────

    @patch("b2b_client.send_blocked_event")
    def test_soft_block_unknown_reason_returns_400(self, mock_send):
        """
        Non-existent blocking_reason_id → 400; B2B must NOT be called.
        """
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(
            _block_url(self.ticket.id),
            {
                "blocking_reason_ids": [str(uuid.uuid4())],  # random, doesn't exist
                "comment": "Test",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["code"], "BLOCKING_REASON_NOT_FOUND")
        mock_send.assert_not_called()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_REVIEW)

    # ── unhappy: wrong moderator ───────────────────────────────────────────────

    @patch("b2b_client.send_blocked_event")
    def test_soft_block_others_card_returns_403(self, mock_send):
        """
        A moderator cannot soft-block a ticket assigned to someone else.
        """
        other = _make_moderator("mod_other")
        self.client.force_authenticate(user=other)

        resp = self.client.post(
            _block_url(self.ticket.id),
            {
                "blocking_reason_ids": [str(self.soft_reason.id)],
                "comment": "Trying to block someone else's ticket",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], "FORBIDDEN")
        mock_send.assert_not_called()

    # ── unhappy: invalid field_name in field_reports ──────────────────────────

    @patch("b2b_client.send_blocked_event")
    def test_soft_block_invalid_field_name_returns_400(self, mock_send):
        """
        field_reports[].field_name must be in the allowed enum.
        An unknown field_name → 400, ticket unchanged, B2B not called.
        """
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(
            _block_url(self.ticket.id),
            {
                "blocking_reason_ids": [str(self.soft_reason.id)],
                "comment": "Bad field",
                "field_reports": [
                    {"field_name": "totally_invalid_field", "comment": "oops"},
                ],
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["code"], "INVALID_FIELD_NAME")
        mock_send.assert_not_called()
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_REVIEW)

    # ── ADR route: hard reason → HARD_BLOCKED ─────────────────────────────────

    @patch("b2b_client.send_blocked_event")
    def test_soft_block_hard_only_reason_routes_to_hard(self, mock_send):
        """
        If the chosen BlockingReason has hard_block=True, the endpoint
        silently routes to HARD_BLOCKED (ADR choice B: unified endpoint,
        reason catalogue is the single source of truth).
        B2B event carries hard_block=True.
        """
        hard_reason = _make_hard_reason()
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(
            _block_url(self.ticket.id),
            {
                "blocking_reason_ids": [str(hard_reason.id)],
                "comment": "Товар оказался контрафактом",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], TicketStatus.HARD_BLOCKED)

        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.is_terminal())

        _, kwargs = mock_send.call_args
        self.assertTrue(kwargs["hard_block"])
