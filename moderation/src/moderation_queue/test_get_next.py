"""
US-MOD-02: Get next ticket from moderation queue.

POST /api/v1/product-moderation/get-next

Covered:
  next_returns_oldest_pending              — oldest PENDING → IN_REVIEW, assigned to caller
  concurrent_two_moderators_get_different_cards — two moderators claim two different tickets
  empty_queue_returns_204                  — no PENDING tickets → 204
  moderator_already_has_in_review_returns_409 — second call with active IN_REVIEW → 409
"""
import uuid

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import BlockingReason, Ticket, TicketKind, TicketStatus

URL = "/api/v1/product-moderation/get-next"


def _make_moderator(username: str) -> User:
    return User.objects.create_user(username=username, password="pass!")


def _make_pending_ticket(queue_priority: int = 1, **kwargs) -> Ticket:
    return Ticket.objects.create(
        product_id=uuid.uuid4(),
        seller_id=uuid.uuid4(),
        kind=TicketKind.CREATE,
        status=TicketStatus.PENDING,
        queue_priority=queue_priority,
        json_after={"title": "Test product"},
        **kwargs,
    )


class GetNextTicketTests(APITestCase):

    def setUp(self):
        self.moderator = _make_moderator("mod_alice")
        self.client.force_authenticate(user=self.moderator)

    # ── happy path ─────────────────────────────────────────────────────────────

    def test_next_returns_oldest_pending(self):
        """
        Oldest PENDING ticket transitions to IN_REVIEW, assigned to caller.
        Response contains product_moderation_id, status=IN_REVIEW, queue_priority.
        """
        # Create two PENDING tickets; older one should be returned first
        old_ticket = _make_pending_ticket(queue_priority=1)
        _make_pending_ticket(queue_priority=1)

        resp = self.client.post(URL, {}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], TicketStatus.IN_REVIEW)
        self.assertEqual(str(resp.data["product_moderation_id"]), str(old_ticket.id))
        self.assertIn("json_after", resp.data)
        self.assertIn("date_created", resp.data)
        self.assertIn("date_updated", resp.data)

        old_ticket.refresh_from_db()
        self.assertEqual(old_ticket.status, TicketStatus.IN_REVIEW)
        self.assertEqual(old_ticket.assigned_moderator_id, self.moderator.pk)
        self.assertIsNotNone(old_ticket.claimed_at)
        self.assertIsNotNone(old_ticket.claim_expires_at)

    def test_specific_queue_id_respected(self):
        """queueId=2 returns only from queue 2, even if queue 1 has tickets."""
        q1_ticket = _make_pending_ticket(queue_priority=1)
        q2_ticket = _make_pending_ticket(queue_priority=2)

        resp = self.client.post(URL, {"queueId": 2}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(str(resp.data["product_moderation_id"]), str(q2_ticket.id))
        q1_ticket.refresh_from_db()
        self.assertEqual(q1_ticket.status, TicketStatus.PENDING)  # untouched

    def test_auto_priority_falls_through_to_next_queue(self):
        """No queueId → tries 1, 2, 3, 4; returns from first non-empty."""
        q3_ticket = _make_pending_ticket(queue_priority=3)

        resp = self.client.post(URL, {}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(str(resp.data["product_moderation_id"]), str(q3_ticket.id))

    # ── concurrent access ─────────────────────────────────────────────────────

    def test_concurrent_two_moderators_get_different_cards(self):
        """
        Two moderators calling get-next sequentially each receive a distinct ticket.
        (True SQL-level concurrency is verified via SELECT FOR UPDATE SKIP LOCKED;
        here we confirm the sequential invariant: once a ticket is IN_REVIEW it
        cannot be claimed by a second moderator.)
        """
        mod_bob = _make_moderator("mod_bob")
        t1 = _make_pending_ticket(queue_priority=1)
        t2 = _make_pending_ticket(queue_priority=1)

        # Alice claims first
        self.client.force_authenticate(user=self.moderator)
        resp_a = self.client.post(URL, {}, format="json")
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        alice_id = resp_a.data["product_moderation_id"]

        # Bob claims second
        self.client.force_authenticate(user=mod_bob)
        resp_b = self.client.post(URL, {}, format="json")
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        bob_id = resp_b.data["product_moderation_id"]

        self.assertNotEqual(alice_id, bob_id, "Both moderators must receive different tickets")
        self.assertIn(str(t1.id), [alice_id, bob_id])
        self.assertIn(str(t2.id), [alice_id, bob_id])

    # ── empty queue ────────────────────────────────────────────────────────────

    def test_empty_queue_returns_204(self):
        """No PENDING tickets in any queue → 204 No Content."""
        resp = self.client.post(URL, {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_empty_specific_queue_returns_204(self):
        """PENDING exists in queue 2, but queueId=1 requested → 204."""
        _make_pending_ticket(queue_priority=2)
        resp = self.client.post(URL, {"queueId": 1}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    # ── moderator already in review ────────────────────────────────────────────

    def test_moderator_already_has_in_review_returns_409(self):
        """
        If the caller already has an IN_REVIEW ticket, a second get-next
        returns 409 ALREADY_IN_REVIEW to prevent parallel reviews.
        """
        existing = Ticket.objects.create(
            product_id=uuid.uuid4(),
            seller_id=uuid.uuid4(),
            kind=TicketKind.CREATE,
            status=TicketStatus.IN_REVIEW,
            assigned_moderator=self.moderator,
            json_after={"title": "Current review"},
        )
        _make_pending_ticket(queue_priority=1)

        resp = self.client.post(URL, {}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data["code"], "ALREADY_IN_REVIEW")
        self.assertEqual(str(resp.data["ticket_id"]), str(existing.id))

    # ── invalid queueId ────────────────────────────────────────────────────────

    def test_invalid_queue_id_returns_400(self):
        """queueId=5 is out of range → 400."""
        resp = self.client.post(URL, {"queueId": 5}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["code"], "INVALID_QUEUE")

    # ── blocking_history for re-submitted product ──────────────────────────────

    def test_blocking_history_populated_for_previously_blocked_ticket(self):
        """
        Queue 2 (re-submitted after soft-block): blocking_history is non-null.
        Queue 1 (new product): blocking_history is null.
        """
        reason = BlockingReason.objects.create(
            code="BAD_PHOTOS",
            title="Фото не соответствуют товару",
            hard_block=False,
        )
        ticket = _make_pending_ticket(
            queue_priority=2,
            blocking_reason=reason,
            json_before={"title": "Old version"},
        )

        resp = self.client.post(URL, {"queueId": 2}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        bh = resp.data["blocking_history"]
        self.assertIsNotNone(bh)
        self.assertEqual(bh["blocking_reason"]["title"], "Фото не соответствуют товару")

    def test_blocking_history_null_for_new_product(self):
        ticket = _make_pending_ticket(queue_priority=1)

        resp = self.client.post(URL, {}, format="json")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["blocking_history"])

    # ── unauthenticated ────────────────────────────────────────────────────────

    def test_unauthenticated_returns_401(self):
        from rest_framework.test import APIClient
        resp = APIClient().post(URL, {}, format="json")
        self.assertIn(resp.status_code, (401, 403))
