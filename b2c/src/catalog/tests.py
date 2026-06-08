from unittest.mock import patch
from urllib.error import URLError

from django.test import TestCase
from rest_framework.test import APIClient


PRODUCT_ID = "bc3fc1b9-873a-4651-9483-7249bd5173df"
SKU_ID = "62fbcabb-be0e-479e-a33b-b848c75da7e0"


def _b2b_product(active_quantity=5, include_sensitive=True, images=None):
    """Build a minimal B2B PublicProductSerializer payload."""
    sku: dict = {
        "id": SKU_ID,
        "name": "256GB Black",
        "price": 12_999_000,
        "discount": 0,
        "image": "https://example.com/iphone-black.jpg",
        "active_quantity": active_quantity,
        "characteristics": [{"name": "Цвет", "value": "Чёрный"}],
    }
    if include_sensitive:
        sku["cost_price"] = 10_000_000
        sku["reserved_quantity"] = 2

    return {
        "id": PRODUCT_ID,
        "title": "iPhone 15 Pro Max",
        "description": "Флагман Apple",
        "min_price": 12_999_000,
        "images": images
        if images is not None
        else [
            {
                "id": "aaaaaaaa-0000-0000-0000-000000000001",
                "url": "https://example.com/iphone.jpg",
                "ordering": 0,
            }
        ],
        "characteristics": [{"name": "Бренд", "value": "Apple"}],
        "skus": [sku],
    }


class ProductCardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = f"/api/v1/catalog/products/{PRODUCT_ID}"

    # ── happy path ────────────────────────────────────────────────────────────

    @patch("catalog.views._fetch_from_b2b")
    def test_product_card_returns_full_data_with_skus(self, mock_fetch):
        mock_fetch.return_value = (200, {"items": [_b2b_product(active_quantity=5)]})

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        # B2B title mapped → B2C name
        self.assertEqual(response.data["name"], "iPhone 15 Pro Max")
        self.assertEqual(len(response.data["skus"]), 1)
        self.assertEqual(response.data["skus"][0]["price"], 12_999_000)
        # active_quantity → available_quantity
        self.assertEqual(response.data["skus"][0]["available_quantity"], 5)
        self.assertTrue(response.data["skus"][0]["in_stock"])
        # top-level computed fields
        self.assertEqual(response.data["min_price"], 12_999_000)
        self.assertTrue(response.data["has_stock"])

    # ── sensitive field isolation ─────────────────────────────────────────────

    @patch("catalog.views._fetch_from_b2b")
    def test_cost_price_absent_in_response(self, mock_fetch):
        mock_fetch.return_value = (200, {"items": [_b2b_product(include_sensitive=True)]})

        response = self.client.get(self.url)

        sku = response.data["skus"][0]
        self.assertNotIn("cost_price", sku)
        self.assertNotIn("reserved_quantity", sku)

    # ── 404 when product not found or invisible ───────────────────────────────

    @patch("catalog.views._fetch_from_b2b")
    def test_blocked_product_returns_404(self, mock_fetch):
        mock_fetch.return_value = (200, {"items": []})

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "PRODUCT_NOT_FOUND")

    # ── zero-stock SKU ────────────────────────────────────────────────────────

    @patch("catalog.views._fetch_from_b2b")
    def test_sku_without_stock_is_shown_as_unavailable(self, mock_fetch):
        mock_fetch.return_value = (200, {"items": [_b2b_product(active_quantity=0)]})

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["skus"][0]["in_stock"])
        self.assertEqual(response.data["skus"][0]["available_quantity"], 0)
        # top-level computed fields reflect zero stock
        self.assertFalse(response.data["has_stock"])
        self.assertIsNone(response.data["min_price"])

    # ── B2B non-200 error diagnostics ─────────────────────────────────────────

    @patch("catalog.views._fetch_from_b2b")
    def test_b2b_403_returns_502_not_404(self, mock_fetch):
        mock_fetch.return_value = (403, {})

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "B2B_ERROR")

    # ── B2B unavailable ───────────────────────────────────────────────────────

    @patch("catalog.views._fetch_from_b2b")
    def test_b2b_unavailable_returns_503(self, mock_fetch):
        mock_fetch.side_effect = URLError("connection refused")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "B2B_UNAVAILABLE")
