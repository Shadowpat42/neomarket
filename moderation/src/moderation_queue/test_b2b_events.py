"""
US-MOD-01 tests: Incoming B2B product events (POST /api/v1/b2b/events)

Covered scenarios:
  created_pending               — PRODUCT_CREATED creates ticket in PENDING
  edited_returns_to_review      — PRODUCT_EDITED after APPROVED resets to PENDING
  edited_updates_in_review      — PRODUCT_EDITED while IN_REVIEW → stays PENDING (re-queued)
  deleted_archived              — PRODUCT_DELETED removes ticket from queue
  duplicate_event_no_side_effects — same idempotency_key → 202, no duplicate effects
  missing_service_header_401    — request without X-Service-Key → 401
"""

import uuid
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import IncomingEventLog, Ticket, TicketKind, TicketStatus

B2B_EVENTS_URL = "/api/v1/b2b/events"
SVC_HEADERS = {"HTTP_X_SERVICE_KEY": "b2b_to_mod_key"}

PRODUCT_ID = str(uuid.uuid4())
SELLER_ID = str(uuid.uuid4())

SAMPLE_JSON_AFTER = {"title": "Awesome product", "skus": [{"id": str(uuid.uuid4())}]}
SAMPLE_JSON_AFTER_V2 = {"title": "Awesome product v2", "skus": [{"id": str(uuid.uuid4())}]}


def _created_payload(product_id=PRODUCT_ID, seller_id=SELLER_ID, idem_key=None, json_after=None):
    return {
        "event_type": "PRODUCT_CREATED",
        "idempotency_key": str(idem_key or uuid.uuid4()),
        "occurred_at": "2026-06-11T00:00:00.000Z",
        "payload": {
            "product_id": product_id,
            "seller_id": seller_id,
            "json_after": json_after or SAMPLE_JSON_AFTER,
        },
    }


def _edited_payload(product_id=PRODUCT_ID, seller_id=SELLER_ID, idem_key=None, json_after=None):
    return {
        "event_type": "PRODUCT_EDITED",
        "idempotency_key": str(idem_key or uuid.uuid4()),
        "occurred_at": "2026-06-11T01:00:00.000Z",
        "payload": {
            "product_id": product_id,
            "seller_id": seller_id,
            "json_before": SAMPLE_JSON_AFTER,
            "json_after": json_after or SAMPLE_JSON_AFTER_V2,
        },
    }


def _deleted_payload(product_id=PRODUCT_ID, idem_key=None):
    return {
        "event_type": "PRODUCT_DELETED",
        "idempotency_key": str(idem_key or uuid.uuid4()),
        "occurred_at": "2026-06-11T02:00:00.000Z",
        "payload": {"product_id": product_id},
    }


def _make_ticket(product_id=PRODUCT_ID, ticket_status=TicketStatus.PENDING, moderator=None):
    return Ticket.objects.create(
        product_id=product_id,
        seller_id=SELLER_ID,
        kind=TicketKind.CREATE,
        status=ticket_status,
        assigned_moderator=moderator,
        json_after=SAMPLE_JSON_AFTER,
        queue_priority=3,
    )


@override_settings(B2B_TO_MOD_KEY="b2b_to_mod_key")
class B2BEventTests(APITestCase):

    # ── US-MOD-01 DoD: created_pending ────────────────────────────────────────

    def test_created_pending(self):
        """
        PRODUCT_CREATED: Moderation creates a PENDING ticket with json_after
        from the event payload. No existing ticket exists.
        """
        product_id = str(uuid.uuid4())
        resp = self.client.post(
            B2B_EVENTS_URL,
            _created_payload(product_id=product_id),
            format="json",
            **SVC_HEADERS,
        )

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        ticket = Ticket.objects.get(product_id=product_id)
        self.assertEqual(ticket.status, TicketStatus.PENDING)
        self.assertEqual(ticket.kind, TicketKind.CREATE)
        self.assertIsNone(ticket.json_before)
        self.assertEqual(ticket.json_after, SAMPLE_JSON_AFTER)
        self.assertIsNone(ticket.assigned_moderator)

    # ── US-MOD-01 DoD: edited_returns_to_review ───────────────────────────────

    def test_edited_returns_to_review(self):
        """
        PRODUCT_EDITED after APPROVED: ticket resets to PENDING so a moderator
        re-reviews the updated version.  json_before←old json_after; json_after←new.
        Assigned moderator is cleared so the ticket goes back into the queue.
        Queue priority → 3 (previously approved product editing).
        """
        moderator = User.objects.create_user("mod_edited", password="pass")
        product_id = str(uuid.uuid4())
        ticket = _make_ticket(product_id=product_id, ticket_status=TicketStatus.APPROVED, moderator=moderator)

        resp = self.client.post(
            B2B_EVENTS_URL,
            _edited_payload(product_id=product_id, json_after=SAMPLE_JSON_AFTER_V2),
            format="json",
            **SVC_HEADERS,
        )

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.PENDING)
        self.assertEqual(ticket.json_before, SAMPLE_JSON_AFTER)
        self.assertEqual(ticket.json_after, SAMPLE_JSON_AFTER_V2)
        self.assertIsNone(ticket.assigned_moderator)
        self.assertEqual(ticket.queue_priority, 3)

    # ── US-MOD-01 DoD: edited_updates_in_review ──────────────────────────────

    def test_edited_updates_in_review(self):
        """
        PRODUCT_EDITED while IN_REVIEW: ticket is reset to PENDING and
        re-joins the queue with its current priority (moderator is released).
        """
        moderator = User.objects.create_user("mod_inreview", password="pass")
        product_id = str(uuid.uuid4())
        ticket = _make_ticket(product_id=product_id, ticket_status=TicketStatus.IN_REVIEW, moderator=moderator)
        ticket.queue_priority = 2
        ticket.save(update_fields=["queue_priority"])

        resp = self.client.post(
            B2B_EVENTS_URL,
            _edited_payload(product_id=product_id),
            format="json",
            **SVC_HEADERS,
        )

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.PENDING)
        # Priority kept for in-queue re-edit
        self.assertEqual(ticket.queue_priority, 2)
        self.assertIsNone(ticket.assigned_moderator)

    # ── US-MOD-01 DoD: deleted_archived ──────────────────────────────────────

    def test_deleted_archived(self):
        """
        PRODUCT_DELETED: all ticket records for the product are removed.
        Calling DELETED twice is idempotent (second call also 202).
        """
        product_id = str(uuid.uuid4())
        _make_ticket(product_id=product_id, ticket_status=TicketStatus.PENDING)

        resp = self.client.post(
            B2B_EVENTS_URL,
            _deleted_payload(product_id=product_id),
            format="json",
            **SVC_HEADERS,
        )

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertFalse(Ticket.objects.filter(product_id=product_id).exists())

        # Idempotent second call
        resp2 = self.client.post(
            B2B_EVENTS_URL,
            _deleted_payload(product_id=product_id),
            format="json",
            **SVC_HEADERS,
        )
        self.assertEqual(resp2.status_code, status.HTTP_202_ACCEPTED)

    # ── US-MOD-01 DoD: duplicate_event_no_side_effects ───────────────────────

    def test_duplicate_event_no_side_effects(self):
        """
        Repeating a PRODUCT_CREATED event with the same idempotency_key
        is acknowledged (202) without creating a second ticket.
        """
        product_id = str(uuid.uuid4())
        idem_key = uuid.uuid4()
        payload = _created_payload(product_id=product_id, idem_key=idem_key)

        resp1 = self.client.post(B2B_EVENTS_URL, payload, format="json", **SVC_HEADERS)
        self.assertEqual(resp1.status_code, status.HTTP_202_ACCEPTED)

        resp2 = self.client.post(B2B_EVENTS_URL, payload, format="json", **SVC_HEADERS)
        self.assertEqual(resp2.status_code, status.HTTP_202_ACCEPTED)

        # Exactly one ticket and one idempotency record
        self.assertEqual(Ticket.objects.filter(product_id=product_id).count(), 1)
        self.assertEqual(IncomingEventLog.objects.filter(idempotency_key=idem_key).count(), 1)

    # ── US-MOD-01 DoD: missing_service_header_401 ────────────────────────────

    def test_missing_service_header_401(self):
        """
        Requests without X-Service-Key (or with wrong key) are rejected with 401.
        No ticket must be created.
        """
        product_id = str(uuid.uuid4())

        # No header at all
        resp_no_key = self.client.post(
            B2B_EVENTS_URL,
            _created_payload(product_id=product_id),
            format="json",
        )
        self.assertEqual(resp_no_key.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(resp_no_key.data["code"], "UNAUTHORIZED")

        # Wrong key
        resp_wrong_key = self.client.post(
            B2B_EVENTS_URL,
            _created_payload(product_id=product_id),
            format="json",
            HTTP_X_SERVICE_KEY="wrong-key",
        )
        self.assertEqual(resp_wrong_key.status_code, status.HTTP_401_UNAUTHORIZED)

        self.assertFalse(Ticket.objects.filter(product_id=product_id).exists())

    # ── Extra: BLOCKED product edit raises priority ───────────────────────────

    def test_edited_after_blocked_sets_priority_2(self):
        """
        When a BLOCKED product is resubmitted (seller fixed the issue),
        priority is bumped to 2 so moderators see it sooner.
        """
        product_id = str(uuid.uuid4())
        ticket = _make_ticket(product_id=product_id, ticket_status=TicketStatus.BLOCKED)
        ticket.queue_priority = 3
        ticket.save(update_fields=["queue_priority"])

        self.client.post(
            B2B_EVENTS_URL,
            _edited_payload(product_id=product_id),
            format="json",
            **SVC_HEADERS,
        )

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.PENDING)
        self.assertEqual(ticket.queue_priority, 2)
