from unittest.mock import patch
from urllib.error import URLError

from django.test import TestCase
from rest_framework.test import APIClient

from cart.models import CartItem
from .models import Order, OrderItem

PRODUCT_ID = "bc3fc1b9-873a-4651-9483-7249bd5173df"
SKU_ID = "62fbcabb-be0e-479e-a33b-b848c75da7e0"
USER_ID = "556f051a-baee-4b0f-bd41-555b5e01e6f4"


def b2b_products_response(active_quantity=5, price=12999000, discount=0):
    return {
        "items": [
            {
                "id": PRODUCT_ID,
                "title": "iPhone 15 Pro Max",
                "skus": [
                    {
                        "id": SKU_ID,
                        "name": "256GB Black",
                        "price": price,
                        "discount": discount,
                        "active_quantity": active_quantity,
                    }
                ],
            }
        ]
    }


class CheckoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/orders"
        self.headers = {
            "HTTP_X_USER_ID": USER_ID,
        }

    @patch("orders.views.b2b_reserve")
    @patch("orders.views.b2b_get_products")
    def test_checkout_creates_paid_order_with_fixed_prices(self, mock_get_products, mock_reserve):
        mock_get_products.return_value = b2b_products_response(
            active_quantity=5,
            price=12999000,
            discount=1000000,
        )
        mock_reserve.return_value = (
            200,
            {
                "order_id": "order-id",
                "status": "RESERVED",
                "reserved_at": "2026-06-10T00:00:00Z",
            },
        )

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=2,
        )

        response = self.client.post(
            self.url,
            {"idempotency_key": "checkout-key-1"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "PAID")
        self.assertEqual(response.data["total_amount"], 23998000)

        order = Order.objects.get(id=response.data["id"])
        item = OrderItem.objects.get(order=order)

        self.assertEqual(item.unit_price, 11999000)
        self.assertEqual(item.line_total, 23998000)
        self.assertEqual(item.product_title, "iPhone 15 Pro Max")
        self.assertEqual(item.sku_name, "256GB Black")

    @patch("orders.views.b2b_reserve")
    @patch("orders.views.b2b_get_products")
    def test_partial_reserve_failure_returns_409(self, mock_get_products, mock_reserve):
        mock_get_products.return_value = b2b_products_response(active_quantity=5)
        mock_reserve.return_value = (
            409,
            {
                "code": "INSUFFICIENT_STOCK",
                "message": "Недостаточно остатка",
                "details": {
                    "failed_items": [
                        {
                            "sku_id": SKU_ID,
                            "reason": "INSUFFICIENT_STOCK",
                        }
                    ]
                },
            },
        )

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=2,
        )

        response = self.client.post(
            self.url,
            {"idempotency_key": "checkout-key-2"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "RESERVE_FAILED")
        self.assertIn("failed_items", response.data["details"]["details"])

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

    @patch("orders.views.b2b_reserve")
    @patch("orders.views.b2b_get_products")
    def test_idempotency_returns_existing_order(self, mock_get_products, mock_reserve):
        mock_get_products.return_value = b2b_products_response(active_quantity=5)
        mock_reserve.return_value = (
            200,
            {
                "order_id": "order-id",
                "status": "RESERVED",
                "reserved_at": "2026-06-10T00:00:00Z",
            },
        )

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=1,
        )

        body = {"idempotency_key": "same-checkout-key"}

        response1 = self.client.post(
            self.url,
            body,
            format="json",
            **self.headers,
        )

        response2 = self.client.post(
            self.url,
            body,
            format="json",
            **self.headers,
        )

        self.assertEqual(response1.status_code, 201)
        self.assertEqual(response2.status_code, 200)

        self.assertEqual(response1.data["id"], response2.data["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

    @patch("orders.views.b2b_get_products")
    def test_b2b_unavailable_returns_503(self, mock_get_products):
        mock_get_products.side_effect = URLError("B2B unavailable")

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=1,
        )

        response = self.client.post(
            self.url,
            {"idempotency_key": "checkout-key-3"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "B2B_UNAVAILABLE")


class CancelOrderTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.headers = {
            "HTTP_X_USER_ID": USER_ID,
        }

    def create_order(self, status_value="PAID", user_id=USER_ID):
        order = Order.objects.create(
            user_id=user_id,
            idempotency_key=f"cancel-test-{status_value}-{user_id}",
            status=status_value,
            total_amount=12999000,
        )

        OrderItem.objects.create(
            order=order,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            product_title="iPhone 15 Pro Max",
            sku_name="256GB Black",
            quantity=1,
            unit_price=12999000,
            line_total=12999000,
        )

        return order

    @patch("orders.views.b2b_unreserve")
    def test_cancel_paid_order_transitions_to_cancelled(self, mock_unreserve):
        mock_unreserve.return_value = (
            200,
            {
                "order_id": "order-id",
                "status": "UNRESERVED",
                "processed_at": "2026-06-10T00:00:00Z",
            },
        )

        order = self.create_order(status_value="PAID")

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Передумал"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()

        self.assertEqual(order.status, "CANCELLED")
        self.assertEqual(order.cancel_reason, "Передумал")
        self.assertIsNotNone(order.cancelled_at)

        self.assertEqual(response.data["status"], "CANCELLED")

    @patch("orders.views.b2b_unreserve")
    def test_unreserve_failure_transitions_to_cancel_pending(self, mock_unreserve):
        mock_unreserve.side_effect = URLError("B2B unavailable")

        order = self.create_order(status_value="PAID")

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Не нужен"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 202)

        order.refresh_from_db()

        self.assertEqual(order.status, "CANCEL_PENDING")
        self.assertEqual(order.cancel_reason, "Не нужен")

        self.assertEqual(response.data["status"], "CANCEL_PENDING")

    @patch("orders.views.b2b_unreserve")
    def test_cancel_assembling_order_transitions_to_cancelled(self, mock_unreserve):
        mock_unreserve.return_value = (
            200,
            {
                "order_id": "order-id",
                "status": "UNRESERVED",
                "processed_at": "2026-06-10T00:00:00Z",
            },
        )

        order = self.create_order(status_value="ASSEMBLING")

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Передумал"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)

        order.refresh_from_db()

        self.assertEqual(order.status, "CANCELLED")
        self.assertEqual(response.data["status"], "CANCELLED")
        mock_unreserve.assert_called_once()

    @patch("orders.views.b2b_unreserve")
    def test_cancel_delivered_order_returns_409(self, mock_unreserve):
        order = self.create_order(status_value="DELIVERED")

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Передумал"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "CANCEL_NOT_ALLOWED")
        self.assertEqual(response.data["details"]["current_status"], "DELIVERED")

        mock_unreserve.assert_not_called()

    @patch("orders.views.b2b_unreserve")
    def test_other_user_order_returns_404(self, mock_unreserve):
        other_user_id = "11111111-1111-1111-1111-111111111111"

        order = self.create_order(
            status_value="PAID",
            user_id=other_user_id,
        )

        response = self.client.post(
            f"/api/v1/orders/{order.id}/cancel",
            {"reason": "Пытаюсь отменить чужой"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "ORDER_NOT_FOUND")

        mock_unreserve.assert_not_called()
