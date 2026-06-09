"""
US-MOD-03 tests: Approve ticket (POST /api/v1/tickets/{ticket_id}/approve)

Covered scenarios:
  approve_transitions_to_moderated_and_emits_event  — happy path
  approve_others_card_returns_403                   — wrong moderator → 403
  approve_after_edited_returns_409                  — ticket not IN_REVIEW → 409
  approve_without_sku_returns_409                   — product has 0 SKUs → 409
"""

import uuid
from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Ticket, TicketKind, TicketStatus


def _approve_url(ticket_id):
    return f"/api/v1/tickets/{ticket_id}/approve"


def _make_moderator(username: str) -> User:
    return User.objects.create_user(username=username, password="testpass123!")


def _make_ticket(moderator: User, ticket_status: str = TicketStatus.IN_REVIEW) -> Ticket:
    return Ticket.objects.create(
        product_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        kind=TicketKind.CREATE,
        status=ticket_status,
        assigned_moderator=moderator,
        json_after={"title": "Test product"},
    )


class ApproveTicketTests(APITestCase):

    def setUp(self):
        self.moderator = _make_moderator("mod_alice")
        self.ticket = _make_ticket(self.moderator)

    # ── happy path ─────────────────────────────────────────────────────────────

    @patch("moderation_queue.views._fetch_sku_count", return_value=2)
    @patch("b2b_client.send_moderated_event")
    def test_approve_transitions_to_moderated_and_emits_event(
        self, mock_send, mock_sku
    ):
        """
        Happy path: status transitions to APPROVED, B2B event is sent,
        response contains product_id and status=APPROVED.
        """
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(
            _approve_url(self.ticket.id),
            {"comment": "All good"},
            format="json",
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], TicketStatus.APPROVED)
        self.assertEqual(str(resp.data["product_id"]), str(self.ticket.product_id))

        # Ticket persisted as APPROVED
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.APPROVED)
        self.assertIsNotNone(self.ticket.decision_at)
        self.assertEqual(self.ticket.decision_comment, "All good")

        # B2B notified exactly once with correct product_id
        mock_send.assert_called_once_with(
            product_id=self.ticket.product_id,
            idempotency_key=self.ticket.id,
            moderator_comment="All good",
        )

    # ── unhappy: wrong moderator ───────────────────────────────────────────────

    @patch("moderation_queue.views._fetch_sku_count", return_value=1)
    @patch("b2b_client.send_moderated_event")
    def test_approve_others_card_returns_403(self, mock_send, mock_sku):
        """
        A moderator cannot approve a ticket assigned to someone else.
        """
        other_moderator = _make_moderator("mod_bob")
        self.client.force_authenticate(user=other_moderator)

        resp = self.client.post(_approve_url(self.ticket.id), format="json")

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], "FORBIDDEN")
        # B2B must NOT be called
        mock_send.assert_not_called()
        # Ticket status unchanged
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_REVIEW)

    # ── unhappy: ticket not in IN_REVIEW ──────────────────────────────────────

    @patch("moderation_queue.views._fetch_sku_count", return_value=1)
    @patch("b2b_client.send_moderated_event")
    def test_approve_after_edited_returns_409(self, mock_send, mock_sku):
        """
        If the seller edits the product while it is in review, the ticket
        status is reset to PENDING. Attempting to approve a PENDING ticket → 409.
        (Simulates the "продавец отредактировал во время review" scenario.)
        """
        # Simulate ticket returned to PENDING after a PRODUCT_EDITED event
        ticket = _make_ticket(self.moderator, ticket_status=TicketStatus.PENDING)
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(_approve_url(ticket.id), format="json")

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data["code"], "TICKET_WRONG_STATUS")
        mock_send.assert_not_called()

    # ── unhappy: product has no SKUs ──────────────────────────────────────────

    @patch("moderation_queue.views._fetch_sku_count", return_value=0)
    @patch("b2b_client.send_moderated_event")
    def test_approve_without_sku_returns_409(self, mock_send, mock_sku):
        """
        A product with 0 SKUs cannot be approved (B2B would publish it to catalog
        but customers would see no variants to buy).
        """
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(_approve_url(self.ticket.id), format="json")

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data["code"], "NO_SKUS")
        mock_send.assert_not_called()
        # Ticket must remain IN_REVIEW
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_REVIEW)

    # ── extra: B2B failure rolls back ticket ──────────────────────────────────

    @patch("moderation_queue.views._fetch_sku_count", return_value=1)
    @patch("b2b_client.send_moderated_event", side_effect=OSError("network error"))
    def test_b2b_failure_rolls_back_and_returns_500(self, mock_send, mock_sku):
        """
        If B2B is unreachable, the ticket rolls back to IN_REVIEW and 500 is returned
        so the moderator can retry without double-approving.
        """
        self.client.force_authenticate(user=self.moderator)

        resp = self.client.post(_approve_url(self.ticket.id), format="json")

        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(resp.data["code"], "B2B_UNAVAILABLE")

        # Ticket must be rolled back to IN_REVIEW
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_REVIEW)
