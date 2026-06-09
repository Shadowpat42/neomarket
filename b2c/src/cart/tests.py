from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIClient

from .models import CartItem


PRODUCT_ID = "bc3fc1b9-873a-4651-9483-7249bd5173df"
SKU_ID = "62fbcabb-be0e-479e-a33b-b848c75da7e0"
USER_ID = "556f051a-baee-4b0f-bd41-555b5e01e6f4"
SESSION_ID = "guest-session-123"


def b2b_response(active_quantity=5):
    return {
        "items": [
            {
                "id": PRODUCT_ID,
                "name": "iPhone 15 Pro Max",
                "title": "iPhone 15 Pro Max",
                "slug": "iphone-15",
                "images": [
                    {
                        "id": "aaaaaaaa-0000-0000-0000-000000000001",
                        "url": "https://example.com/iphone.jpg",
                        "ordering": 0,
                    }
                ],
                "skus": [
                    {
                        "id": SKU_ID,
                        "name": "256GB Black",
                        "price": 12999000,
                        "discount": 0,
                        "image": "https://example.com/iphone-black.jpg",
                        "active_quantity": active_quantity,
                    }
                ],
            }
        ]
    }


class CartTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("cart.views.find_sku_in_b2b")
    def test_add_sku_increments_quantity_if_already_in_cart(self, mock_find):
        mock_find.return_value = (
            b2b_response()["items"][0],
            b2b_response()["items"][0]["skus"][0],
        )

        headers = {"HTTP_X_SESSION_ID": SESSION_ID}
        body = {
            "sku_id": SKU_ID,
            "quantity": 2,
        }

        response1 = self.client.post(
            "/api/v1/cart/items",
            body,
            format="json",
            **headers,
        )

        response2 = self.client.post(
            "/api/v1/cart/items",
            body,
            format="json",
            **headers,
        )

        self.assertEqual(response1.status_code, 201)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(response2.data["quantity"], 4)

        item = CartItem.objects.get(session_id=SESSION_ID, sku_id=SKU_ID)
        self.assertEqual(item.quantity, 4)

    @patch("cart.views.fetch_b2b_products")
    def test_get_cart_enriched_with_b2b_data(self, mock_fetch):
        mock_fetch.return_value = b2b_response(active_quantity=5)

        CartItem.objects.create(
            session_id=SESSION_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=2,
        )

        response = self.client.get(
            "/api/v1/cart",
            HTTP_X_SESSION_ID=SESSION_ID,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["items"]), 1)

        item = response.data["items"][0]

        self.assertTrue(item["available"])
        self.assertIsNone(item["unavailable_reason"])
        self.assertEqual(item["line_total"], 25998000)

        self.assertEqual(response.data["summary"]["total_amount"], 25998000)
        self.assertEqual(response.data["summary"]["total_items"], 2)
        self.assertTrue(response.data["summary"]["checkout_ready"])

    @patch("cart.views.fetch_b2b_products")
    def test_unavailable_sku_shown_with_reason(self, mock_fetch):
        mock_fetch.return_value = b2b_response(active_quantity=0)

        CartItem.objects.create(
            session_id=SESSION_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=1,
        )

        response = self.client.get(
            "/api/v1/cart",
            HTTP_X_SESSION_ID=SESSION_ID,
        )

        self.assertEqual(response.status_code, 200)

        item = response.data["items"][0]

        self.assertFalse(item["available"])
        self.assertEqual(item["unavailable_reason"], "OUT_OF_STOCK")
        self.assertEqual(item["line_total"], 0)

        self.assertEqual(response.data["summary"]["total_amount"], 0)
        self.assertEqual(response.data["summary"]["unavailable_count"], 1)
        self.assertFalse(response.data["summary"]["checkout_ready"])

    @patch("cart.views.fetch_b2b_products")
    def test_guest_cart_merged_on_login(self, mock_fetch):
        mock_fetch.return_value = b2b_response(active_quantity=5)

        CartItem.objects.create(
            session_id=SESSION_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=2,
        )

        CartItem.objects.create(
            user_id=USER_ID,
            product_id=PRODUCT_ID,
            sku_id=SKU_ID,
            quantity=5,
        )

        response = self.client.post(
            "/api/v1/cart/merge",
            HTTP_X_SESSION_ID=SESSION_ID,
            HTTP_X_USER_ID=USER_ID,
        )

        self.assertEqual(response.status_code, 200)

        auth_item = CartItem.objects.get(user_id=USER_ID, sku_id=SKU_ID)
        self.assertEqual(auth_item.quantity, 5)

        guest_exists = CartItem.objects.filter(session_id=SESSION_ID).exists()
        self.assertFalse(guest_exists)