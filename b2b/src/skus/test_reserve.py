import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Product
from shared_models.models import BaseProductStatus
from skus.models import SKU, ReserveOperation

User = get_user_model()

RESERVE_URL = "/api/v1/inventory/reserve"
UNRESERVE_URL = "/api/v1/inventory/unreserve"
B2C_KEY = "test-b2c-inventory-key"


def _svc_headers():
    return {"HTTP_X_SERVICE_KEY": B2C_KEY}


@override_settings(B2C_SERVICE_KEY=B2C_KEY)
class ReserveTests(APITestCase):
    def setUp(self):
        seller = User.objects.create_user(
            email="seller@test.com",
            password="12345678",
            first_name="S",
            last_name="L",
            company_name="Shop",
            phone="+79000000001",
        )
        category = Category.objects.create(name="Electronics")
        self.product = Product.objects.create(
            seller_id=seller.id,
            category=category,
            title="iPhone",
            description="desc",
            status=BaseProductStatus.MODERATED,
            slug="iphone",
        )
        self.sku_a = SKU.objects.create(
            product=self.product,
            name="256GB Black",
            price=100_00,
            cost_price=50_00,
            stock_quantity=10,
            reserved_quantity=0,
        )
        self.sku_b = SKU.objects.create(
            product=self.product,
            name="512GB White",
            price=120_00,
            cost_price=60_00,
            stock_quantity=5,
            reserved_quantity=0,
        )

    def _reserve_payload(self, items, idempotency_key=None, order_id=None):
        return {
            "idempotency_key": str(idempotency_key or uuid.uuid4()),
            "order_id": str(order_id or uuid.uuid4()),
            "items": items,
        }

    # ── happy paths ──────────────────────────────────────────────────────────

    def test_reserve_all_skus_succeeds(self):
        payload = self._reserve_payload(
            items=[
                {"sku_id": str(self.sku_a.id), "quantity": 3},
                {"sku_id": str(self.sku_b.id), "quantity": 2},
            ]
        )

        response = self.client.post(RESERVE_URL, payload, format="json", **_svc_headers())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "RESERVED")
        self.assertIn("items", response.data)

        self.sku_a.refresh_from_db()
        self.sku_b.refresh_from_db()
        self.assertEqual(self.sku_a.reserved_quantity, 3)
        self.assertEqual(self.sku_b.reserved_quantity, 2)
        # active_quantity = stock - reserved
        self.assertEqual(self.sku_a.stock_quantity - self.sku_a.reserved_quantity, 7)
        self.assertEqual(self.sku_b.stock_quantity - self.sku_b.reserved_quantity, 3)

    def test_idempotent_reserve_returns_200_without_double_deduction(self):
        key = uuid.uuid4()
        order_id = uuid.uuid4()
        payload = self._reserve_payload(
            items=[{"sku_id": str(self.sku_a.id), "quantity": 2}],
            idempotency_key=key,
            order_id=order_id,
        )

        resp1 = self.client.post(RESERVE_URL, payload, format="json", **_svc_headers())
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)

        resp2 = self.client.post(RESERVE_URL, payload, format="json", **_svc_headers())
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        # Only one ReserveOperation record
        self.assertEqual(ReserveOperation.objects.filter(idempotency_key=key).count(), 1)

        # SKU reserved_quantity incremented only once
        self.sku_a.refresh_from_db()
        self.assertEqual(self.sku_a.reserved_quantity, 2)

    # ── unhappy paths ─────────────────────────────────────────────────────────

    def test_partial_insufficient_stock_returns_409_all_rollback(self):
        payload = self._reserve_payload(
            items=[
                {"sku_id": str(self.sku_a.id), "quantity": 2},
                {"sku_id": str(self.sku_b.id), "quantity": 100},  # way too many
            ]
        )

        response = self.client.post(RESERVE_URL, payload, format="json", **_svc_headers())

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "INSUFFICIENT_STOCK")
        self.assertIn("details", response.data)
        failed_sku_ids = {f["sku_id"] for f in response.data["details"]["failed_items"]}
        self.assertIn(str(self.sku_b.id), failed_sku_ids)

        # All-or-nothing: sku_a must NOT have been modified
        self.sku_a.refresh_from_db()
        self.sku_b.refresh_from_db()
        self.assertEqual(self.sku_a.reserved_quantity, 0)
        self.assertEqual(self.sku_b.reserved_quantity, 0)

    @patch("skus.inventory.send_sku_out_of_stock_event")
    def test_sku_out_of_stock_event_emitted(self, mock_send):
        # Reserve all remaining stock → active_quantity reaches 0
        payload = self._reserve_payload(
            items=[{"sku_id": str(self.sku_a.id), "quantity": 10}]
        )

        response = self.client.post(RESERVE_URL, payload, format="json", **_svc_headers())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.sku_a.refresh_from_db()
        self.assertEqual(self.sku_a.stock_quantity - self.sku_a.reserved_quantity, 0)

        mock_send.assert_called_once_with(
            sku_id=self.sku_a.id,
            product_id=self.sku_a.product_id,
        )

    # ── unreserve ─────────────────────────────────────────────────────────────

    def test_unreserve_restores_quantities(self):
        # First reserve
        reserve_payload = self._reserve_payload(
            items=[
                {"sku_id": str(self.sku_a.id), "quantity": 3},
                {"sku_id": str(self.sku_b.id), "quantity": 2},
            ]
        )
        self.client.post(RESERVE_URL, reserve_payload, format="json", **_svc_headers())

        self.sku_a.refresh_from_db()
        self.sku_b.refresh_from_db()
        self.assertEqual(self.sku_a.reserved_quantity, 3)
        self.assertEqual(self.sku_b.reserved_quantity, 2)

        # Now unreserve
        order_id = uuid.uuid4()
        unreserve_payload = {
            "order_id": str(order_id),
            "items": [
                {"sku_id": str(self.sku_a.id), "quantity": 3},
                {"sku_id": str(self.sku_b.id), "quantity": 2},
            ],
        }
        resp = self.client.post(
            UNRESERVE_URL, unreserve_payload, format="json", **_svc_headers()
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "UNRESERVED")

        self.sku_a.refresh_from_db()
        self.sku_b.refresh_from_db()
        self.assertEqual(self.sku_a.reserved_quantity, 0)
        self.assertEqual(self.sku_b.reserved_quantity, 0)
        self.assertEqual(self.sku_a.stock_quantity - self.sku_a.reserved_quantity, 10)
        self.assertEqual(self.sku_b.stock_quantity - self.sku_b.reserved_quantity, 5)
