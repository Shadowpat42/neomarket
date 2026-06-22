"""
US-MOD-06: Blocking reasons catalogue.

GET /api/v1/blocking-reasons

Covered:
  list_returns_active_reasons          — active reasons returned with id, code, title, hard_block, is_active
  inactive_reasons_not_visible         — deactivated reasons hidden from API
  referenced_reason_cannot_be_deleted  — soft-delete used when reason has ticket refs
"""
import uuid

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory
from rest_framework import status
from rest_framework.test import APITestCase

from .admin import BlockingReasonAdmin
from .models import BlockingReason, Ticket, TicketKind, TicketStatus

URL = "/api/v1/blocking-reasons"


def _make_reason(code, title, hard_block=False, is_active=True) -> BlockingReason:
    return BlockingReason.objects.create(
        code=code,
        title=title,
        hard_block=hard_block,
        is_active=is_active,
    )


class BlockingReasonsListTests(APITestCase):

    def test_list_returns_active_reasons(self):
        """Active reasons returned; each has id, code, title, hard_block, is_active."""
        r1 = _make_reason("BAD_DESCRIPTION", "Описание не соответствует товару", hard_block=False)
        r2 = _make_reason("COUNTERFEIT", "Контрафактный товар", hard_block=True)

        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp.data, list)
        ids = [str(item["id"]) for item in resp.data]
        self.assertIn(str(r1.id), ids)
        self.assertIn(str(r2.id), ids)

        for item in resp.data:
            self.assertIn("id", item)
            self.assertIn("code", item)
            self.assertIn("title", item)
            self.assertIn("hard_block", item)
            self.assertIn("is_active", item)

    def test_hard_block_flag_correct(self):
        soft = _make_reason("SOFT_R", "Soft reason", hard_block=False)
        hard = _make_reason("HARD_R", "Hard reason", hard_block=True)

        resp = self.client.get(URL)

        by_id = {str(item["id"]): item for item in resp.data}
        self.assertFalse(by_id[str(soft.id)]["hard_block"])
        self.assertTrue(by_id[str(hard.id)]["hard_block"])

    def test_inactive_reasons_not_visible(self):
        active = _make_reason("ACTIVE_R", "Active reason")
        inactive = _make_reason("INACTIVE_R", "Old reason", is_active=False)

        resp = self.client.get(URL)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [str(item["id"]) for item in resp.data]
        self.assertIn(str(active.id), ids)
        self.assertNotIn(str(inactive.id), ids)

    def test_empty_catalogue_returns_empty_list(self):
        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, [])


class BlockingReasonAdminSoftDeleteTests(APITestCase):

    def _make_request(self):
        from django.contrib.messages.storage.cookie import CookieStorage
        request = self.factory.post("/admin/delete/")
        request.user = self.superuser
        request._messages = CookieStorage(request)
        return request

    def setUp(self):
        self.site = AdminSite()
        self.admin = BlockingReasonAdmin(BlockingReason, self.site)
        self.superuser = User.objects.create_superuser("admin", password="admin")
        self.factory = RequestFactory()

    def test_referenced_reason_cannot_be_deleted(self):
        reason = _make_reason("REFERENCED", "Referenced reason")
        ticket = Ticket.objects.create(
            product_id=uuid.uuid4(),
            seller_id=uuid.uuid4(),
            kind=TicketKind.CREATE,
            status=TicketStatus.BLOCKED,
            blocking_reason=reason,
            json_after={},
        )

        self.admin.delete_model(self._make_request(), reason)

        reason.refresh_from_db()
        self.assertFalse(reason.is_active)
        ticket.refresh_from_db()
        self.assertEqual(ticket.blocking_reason_id, reason.id)

    def test_unreferenced_reason_is_hard_deleted(self):
        reason = _make_reason("ORPHAN", "Orphan reason")
        reason_id = reason.id

        self.admin.delete_model(self._make_request(), reason)

        self.assertFalse(BlockingReason.objects.filter(pk=reason_id).exists())
