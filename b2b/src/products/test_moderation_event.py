import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import (
    BlockingReason,
    Category,
    ProcessedModerationEvent,
    Product,
    ProductFieldReport,
)
from shared_models.models import BaseProductStatus
from skus.models import SKU

User = get_user_model()

EVENTS_URL = "/api/v1/moderation/events"
B2B_KEY = "test-b2b-service-key"


def _svc_headers():
    return {"HTTP_X_SERVICE_KEY": B2B_KEY}


@override_settings(B2B_SERVICE_KEY=B2B_KEY)
class ModerationEventTests(APITestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            email="seller@test.com",
            password="password123",
            first_name="Ivan",
            last_name="Ivanov",
            company_name="Shop",
            phone="+79000000001",
        )
        category = Category.objects.create(name="Electronics")
        self.product = Product.objects.create(
            seller_id=self.seller.id,
            category=category,
            title="iPhone 15",
            description="desc",
            status=BaseProductStatus.ON_MODERATION,
            slug="iphone-15",
        )
        self.sku = SKU.objects.create(
            product=self.product,
            name="128GB Black",
            price=100_000,
            cost_price=50_000,
            stock_quantity=10,
        )

    def _post(self, payload):
        return self.client.post(EVENTS_URL, payload, format="json", **_svc_headers())

    # ── happy paths ──────────────────────────────────────────────────────────

    def test_moderated_event_clears_blocking_data(self):
        # Pre-condition: product has stale blocking data
        blocking_reason = BlockingReason.objects.create(title="Wrong description")
        self.product.status = BaseProductStatus.BLOCKED
        self.product.blocking_reason_id = blocking_reason.id
        self.product.moderator_comment = "Fix your photos"
        self.product.save()
        ProductFieldReport.objects.create(
            product=self.product, field_name="description", comment="Plagiarism"
        )

        response = self._post(
            {
                "idempotency_key": str(uuid.uuid4()),
                "product_id": str(self.product.id),
                "event_type": "MODERATED",
            }
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.product.refresh_from_db()
        self.assertEqual(self.product.status, BaseProductStatus.MODERATED)
        self.assertIsNone(self.product.blocking_reason_id)
        self.assertIsNone(self.product.moderator_comment)
        self.assertEqual(self.product.field_reports.count(), 0)

    @patch("products.views.notify_product_blocked", side_effect=None)
    def test_blocked_soft_saves_field_reports(self, mock_notify):
        blocking_reason_id = uuid.uuid4()

        response = self._post(
            {
                "idempotency_key": str(uuid.uuid4()),
                "product_id": str(self.product.id),
                "event_type": "BLOCKED",
                "hard_block": False,
                "blocking_reason": {
                    "id": str(blocking_reason_id),
                    "title": "Description mismatch",
                    "comment": "Text does not match photos",
                },
                "field_reports": [
                    {"field_name": "description", "sku_id": None, "comment": "Plagiarism"},
                    {"field_name": "images[0]", "sku_id": None, "comment": "Low quality"},
                ],
            }
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.product.refresh_from_db()
        self.assertEqual(self.product.status, BaseProductStatus.BLOCKED)
        self.assertEqual(self.product.blocking_reason_id, blocking_reason_id)
        self.assertEqual(self.product.field_reports.count(), 2)

        # B2C was notified
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args.kwargs
        self.assertEqual(str(call_kwargs["product_id"]), str(self.product.id))
        self.assertIn(str(self.sku.id), call_kwargs["sku_ids"])

    @patch("products.views.notify_product_blocked", side_effect=None)
    def test_blocked_hard_sets_terminal_status(self, mock_notify):
        response = self._post(
            {
                "idempotency_key": str(uuid.uuid4()),
                "product_id": str(self.product.id),
                "event_type": "BLOCKED",
                "hard_block": True,
                "blocking_reason": {
                    "id": str(uuid.uuid4()),
                    "title": "Counterfeit goods",
                    "comment": "Selling prohibited items",
                },
            }
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.product.refresh_from_db()
        self.assertEqual(self.product.status, BaseProductStatus.HARD_BLOCKED)
        mock_notify.assert_called_once()

    def test_hard_blocked_product_rejects_seller_edits(self):
        # Mark product as HARD_BLOCKED
        self.product.status = BaseProductStatus.HARD_BLOCKED
        self.product.save()

        # Authenticate as the seller
        refresh = self._get_jwt_for_seller()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh}")

        patch_resp = self.client.patch(
            f"/api/v1/products/{self.product.id}/",
            {"title": "New Title"},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(patch_resp.data["code"], "HARD_BLOCKED")

        delete_resp = self.client.delete(f"/api/v1/products/{self.product.id}/")
        self.assertEqual(delete_resp.status_code, status.HTTP_403_FORBIDDEN)

    # ── unhappy paths ─────────────────────────────────────────────────────────

    def test_duplicate_event_same_idempotency_key_no_side_effects(self):
        idempotency_key = str(uuid.uuid4())

        # First delivery: product moves to MODERATED
        self._post(
            {
                "idempotency_key": idempotency_key,
                "product_id": str(self.product.id),
                "event_type": "MODERATED",
            }
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, BaseProductStatus.MODERATED)

        # Manually change status to simulate a later state change
        self.product.status = BaseProductStatus.ON_MODERATION
        self.product.save()

        # Second delivery with the same key → must NOT change anything
        resp2 = self._post(
            {
                "idempotency_key": idempotency_key,
                "product_id": str(self.product.id),
                "event_type": "MODERATED",
            }
        )
        self.assertEqual(resp2.status_code, status.HTTP_204_NO_CONTENT)

        self.product.refresh_from_db()
        # Status must remain as manually set (ON_MODERATION), not changed again
        self.assertEqual(self.product.status, BaseProductStatus.ON_MODERATION)

        # Exactly one ProcessedModerationEvent record
        self.assertEqual(
            ProcessedModerationEvent.objects.filter(
                idempotency_key=idempotency_key
            ).count(),
            1,
        )

    def test_missing_service_key_returns_401(self):
        response = self.client.post(
            EVENTS_URL,
            {
                "idempotency_key": str(uuid.uuid4()),
                "product_id": str(self.product.id),
                "event_type": "MODERATED",
            },
            format="json",
            # No X-Service-Key header
        )
        # DRF returns 401 when the anonymous user fails a permission check
        # (no authentication credentials provided at all)
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _get_jwt_for_seller(self) -> str:
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(self.seller)
        return str(refresh.access_token)
