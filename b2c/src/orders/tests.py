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