from unittest.mock import patch
from urllib.error import URLError

from django.test import TestCase
from rest_framework.test import APIClient

PRODUCT_ID = "bc3fc1b9-873a-4651-9483-7249bd5173df"
SKU_ID = "62fbcabb-be0e-479e-a33b-b848c75da7e0"
CATEGORY_ID = "d8b8b86f-8d9b-4130-a1b3-9ec62020eb13"


def catalog_b2b_response():
    return {
        "items": [
            {
                "id": PRODUCT_ID,
                "title": "iPhone 15 Pro Max Test 123",
                "slug": "iphone-15-pro-max-test-123",
                "description": "Флагман Apple",
                "status": "MODERATED",
                "category": {
                    "id": CATEGORY_ID,
                    "name": "Смартфоны",
                },
                "images": [
                    {
                        "url": "https://example.com/iphone.jpg",
                        "ordering": 0,
                    }
                ],
                "characteristics": [
                    {
                        "name": "Бренд",
                        "value": "Apple",
                    }
                ],
                "skus": [
                    {
                        "id": SKU_ID,
                        "name": "256GB Black",
                        "price": 12999000,
                        "discount": 0,
                        "image": "https://example.com/iphone-black.jpg",
                        "active_quantity": 5,
                        "characteristics": [
                            {
                                "name": "Цвет",
                                "value": "Чёрный",
                            }
                        ],
                    }
                ],
            }
        ],
        "total_count": 1,
        "limit": 20,
        "offset": 0,
    }


class CatalogFiltersTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("catalog.views._b2b_get")
    def test_catalog_returns_filtered_sorted_products(self, mock_b2b_get):
        mock_b2b_get.return_value = (200, catalog_b2b_response())

        response = self.client.get(
            f"/api/v1/catalog/products?category_id={CATEGORY_ID}&sort=price_asc&limit=20&offset=0"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_count"], 1)
        self.assertEqual(response.data["limit"], 20)
        self.assertEqual(response.data["offset"], 0)

        item = response.data["items"][0]

        self.assertEqual(item["id"], PRODUCT_ID)
        self.assertEqual(item["name"], "iPhone 15 Pro Max Test 123")
        self.assertEqual(item["min_price"], 12999000)
        self.assertTrue(item["has_stock"])
        self.assertEqual(item["skus"][0]["available_quantity"], 5)

    @patch("catalog.views._b2b_get")
    def test_facets_return_counts_per_filter_value(self, mock_b2b_get):
        mock_b2b_get.return_value = (200, catalog_b2b_response())

        response = self.client.get("/api/v1/catalog/facets")

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.data["categories"][0]["id"], CATEGORY_ID)
        self.assertEqual(response.data["categories"][0]["name"], "Смартфоны")
        self.assertEqual(response.data["categories"][0]["count"], 1)

        self.assertEqual(response.data["price"]["min"], 12999000)
        self.assertEqual(response.data["price"]["max"], 12999000)

        self.assertEqual(response.data["characteristics"][0]["name"], "Бренд")
        self.assertEqual(response.data["characteristics"][0]["values"][0]["value"], "Apple")
        self.assertEqual(response.data["characteristics"][0]["values"][0]["count"], 1)

    def test_invalid_sort_returns_400(self):
        response = self.client.get("/api/v1/catalog/products?sort=bad_sort")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "INVALID_SORT")
        self.assertIn("price_asc", response.data["details"]["allowed"])
        self.assertIn("price_desc", response.data["details"]["allowed"])
        self.assertIn("popularity", response.data["details"]["allowed"])
        self.assertIn("new", response.data["details"]["allowed"])

    @patch("catalog.views._b2b_get")
    def test_b2b_unavailable_returns_502(self, mock_b2b_get):
        mock_b2b_get.side_effect = URLError("B2B unavailable")

        response = self.client.get("/api/v1/catalog/products")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "B2B_UNAVAILABLE")


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

    @patch("catalog.views._b2b_get")
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

    @patch("catalog.views._b2b_get")
    def test_cost_price_absent_in_response(self, mock_fetch):
        mock_fetch.return_value = (200, {"items": [_b2b_product(include_sensitive=True)]})

        response = self.client.get(self.url)

        sku = response.data["skus"][0]
        self.assertNotIn("cost_price", sku)
        self.assertNotIn("reserved_quantity", sku)

    # ── 404 when product not found or invisible ───────────────────────────────

    @patch("catalog.views._b2b_get")
    def test_blocked_product_returns_404(self, mock_fetch):
        mock_fetch.return_value = (200, {"items": []})

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "PRODUCT_NOT_FOUND")

    # ── zero-stock SKU ────────────────────────────────────────────────────────

    @patch("catalog.views._b2b_get")
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

    @patch("catalog.views._b2b_get")
    def test_b2b_403_returns_502_not_404(self, mock_fetch):
        mock_fetch.return_value = (403, {})

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "B2B_ERROR")

    # ── B2B unavailable ───────────────────────────────────────────────────────

    @patch("catalog.views._b2b_get")
    def test_b2b_unavailable_returns_503(self, mock_fetch):
        mock_fetch.side_effect = URLError("connection refused")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "B2B_UNAVAILABLE")


class CatalogSearchTests(TestCase):
    """US-CAT-02: Search tests."""

    def setUp(self):
        self.client = APIClient()

    @patch("catalog.views._b2b_get")
    def test_search_returns_matching_products(self, mock_b2b_get):
        mock_b2b_get.return_value = (200, catalog_b2b_response())

        response = self.client.get("/api/v1/catalog/products?search=iphone")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_count"], 1)
        self.assertEqual(response.data["items"][0]["name"], "iPhone 15 Pro Max Test 123")

    def test_short_query_returns_400(self):
        """Search query shorter than 3 characters returns 400."""
        response = self.client.get("/api/v1/catalog/products?search=ab")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "SEARCH_QUERY_TOO_SHORT")
        self.assertIn("min_length", response.data["details"])
        self.assertEqual(response.data["details"]["min_length"], 3)

    @patch("catalog.views._b2b_get")
    def test_special_chars_do_not_break_query(self, mock_b2b_get):
        """Special characters (% , _ , ') should not break the query."""
        mock_b2b_get.return_value = (200, catalog_b2b_response())

        # Test with special characters
        special_queries = ["iPhone%15", "кофе'", "test_"]
        for query in special_queries:
            response = self.client.get(f"/api/v1/catalog/products?search={query}")
            self.assertEqual(response.status_code, 200, f"Query '{query}' should not fail")

    @patch("catalog.views._b2b_get")
    def test_empty_results_returns_200(self, mock_b2b_get):
        """Empty search results should return 200 with empty items list."""
        mock_b2b_get.return_value = (200, {"items": [], "total_count": 0, "limit": 20, "offset": 0})

        response = self.client.get("/api/v1/catalog/products?search=nonexistent")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total_count"], 0)


class SimilarProductsTests(TestCase):
    """US-CAT-04: Similar products tests."""

    def setUp(self):
        self.client = APIClient()
        self.product_id = "bc3fc1b9-873a-4651-9483-7249bd5173df"
        self.category_id = "d8b8b86f-8d9b-4130-a1b3-9ec62020eb13"

    def _get_similar_response(self, product_id, category_id, include_current=True):
        """Helper to build similar products response."""
        items = [
            {
                "id": "similar-1-id",
                "title": "Similar Product 1",
                "slug": "similar-product-1",
                "description": "Similar item",
                "status": "MODERATED",
                "category": {
                    "id": category_id,
                    "name": "Смартфоны",
                },
                "images": [
                    {
                        "url": "https://example.com/similar1.jpg",
                        "ordering": 0,
                    }
                ],
                "skus": [
                    {
                        "id": "sku-similar-1",
                        "name": "Black 128GB",
                        "price": 9999000,
                        "discount": 0,
                        "image": "https://example.com/similar1-black.jpg",
                        "active_quantity": 10,
                    }
                ],
            },
            {
                "id": "similar-2-id",
                "title": "Similar Product 2",
                "slug": "similar-product-2",
                "description": "Another similar item",
                "status": "MODERATED",
                "category": {
                    "id": category_id,
                    "name": "Смартфоны",
                },
                "images": [
                    {
                        "url": "https://example.com/similar2.jpg",
                        "ordering": 0,
                    }
                ],
                "skus": [
                    {
                        "id": "sku-similar-2",
                        "name": "White 256GB",
                        "price": 11999000,
                        "discount": 0,
                        "image": "https://example.com/similar2-white.jpg",
                        "active_quantity": 5,
                    }
                ],
            },
        ]

        if include_current:
            items.append({
                "id": product_id,
                "title": "Current Product",
                "slug": "current-product",
                "description": "Current product",
                "status": "MODERATED",
                "category": {
                    "id": category_id,
                    "name": "Смартфоны",
                },
                "images": [
                    {
                        "url": "https://example.com/current.jpg",
                        "ordering": 0,
                    }
                ],
                "skus": [
                    {
                        "id": "sku-current",
                        "name": "Red 512GB",
                        "price": 14999000,
                        "discount": 0,
                        "image": "https://example.com/current-red.jpg",
                        "active_quantity": 3,
                    }
                ],
            })

        return {
            "items": items,
            "total_count": len(items),
            "limit": 8,
            "offset": 0,
        }

    @patch("catalog.views._b2b_get")
    def test_similar_returns_up_to_8_from_same_category(self, mock_b2b_get):
        """Similar products should return up to 8 from same category, excluding current product."""
        # First call gets current product, second gets similar products
        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {"id": self.category_id},
                }]})
            return (200, self._get_similar_response(self.product_id, self.category_id))

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["items"]), 2)  # Excludes current product
        self.assertEqual(response.data["total_count"], 2)

        # Verify current product is excluded
        for item in response.data["items"]:
            self.assertNotEqual(item["id"], self.product_id)

    @patch("catalog.views._b2b_get")
    def test_empty_category_returns_200_empty_list(self, mock_b2b_get):
        """If no similar products exist, return 200 with empty list."""
        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {"id": self.category_id},
                }]})
            return (200, {"items": [], "total_count": 0, "limit": 8, "offset": 0})

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total_count"], 0)

    @patch("catalog.views._b2b_get")
    def test_unknown_product_returns_404(self, mock_b2b_get):
        """Unknown product should return 404."""
        mock_b2b_get.return_value = (200, {"items": []})

        response = self.client.get("/api/v1/catalog/products/00000000-0000-0000-0000-000000000000/similar")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "PRODUCT_NOT_FOUND")

    @patch("catalog.views._b2b_get")
    def test_similar_products_excludes_current_product(self, mock_b2b_get):
        """Current product should be excluded from similar products."""
        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {"id": self.category_id},
                }]})
            return (200, self._get_similar_response(self.product_id, self.category_id))

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 200)
        product_ids = [item["id"] for item in response.data["items"]]
        self.assertNotIn(self.product_id, product_ids)

    @patch("catalog.views._b2b_get")
    def test_similar_products_limits_to_8(self, mock_b2b_get):
        """Similar products should be limited to 8 items."""
        # Create response with more than 8 items
        items = []
        for i in range(12):
            items.append({
                "id": f"similar-{i}-id",
                "title": f"Similar Product {i}",
                "slug": f"similar-product-{i}",
                "description": f"Similar item {i}",
                "status": "MODERATED",
                "category": {
                    "id": self.category_id,
                    "name": "Смартфоны",
                },
                "images": [{"url": f"https://example.com/similar{i}.jpg", "ordering": 0}],
                "skus": [{
                    "id": f"sku-similar-{i}",
                    "name": f"Variant {i}",
                    "price": 9999000 + i * 100000,
                    "discount": 0,
                    "image": f"https://example.com/similar{i}.jpg",
                    "active_quantity": 10,
                }],
            })

        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {"id": self.category_id},
                }]})
            return (200, {"items": items, "total_count": len(items), "limit": 8, "offset": 0})

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data["items"]), 8)

    @patch("catalog.views._b2b_get")
    def test_similar_products_with_stock_info(self, mock_b2b_get):
        """Similar products should include stock information."""
        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {"id": self.category_id},
                }]})
            return (200, self._get_similar_response(self.product_id, self.category_id))

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 200)
        for item in response.data["items"]:
            self.assertIn("has_stock", item)
            self.assertIn("min_price", item)
            self.assertIn("skus", item)
            for sku in item["skus"]:
                self.assertIn("available_quantity", sku)
                self.assertIn("in_stock", sku)

    @patch("catalog.views._b2b_get")
    def test_similar_products_b2b_unavailable(self, mock_b2b_get):
        """B2B unavailable should return 503."""
        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {"id": self.category_id},
                }]})
            raise URLError("B2B unavailable")

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "B2B_UNAVAILABLE")

    @patch("catalog.views._b2b_get")
    def test_similar_products_b2b_error(self, mock_b2b_get):
        """B2B error should return 502."""
        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {"id": self.category_id},
                }]})
            return (403, {"error": "Forbidden"})

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "B2B_ERROR")

    @patch("catalog.views._b2b_get")
    def test_similar_products_no_category_fallback(self, mock_b2b_get):
        """If product has no category, return empty list."""
        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {},  # No category
                }]})
            # Second call would fail since category_id is empty
            return (200, {"items": [], "total_count": 0, "limit": 8, "offset": 0})

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])

    @patch("catalog.views._b2b_get")
    def test_similar_products_min_price_computation(self, mock_b2b_get):
        """Similar products should compute min_price from available SKUs."""
        def side_effect(path, params=None):
            if params and "ids" in str(params):
                return (200, {"items": [{
                    "id": self.product_id,
                    "title": "Current Product",
                    "category": {"id": self.category_id},
                }]})
            items = [{
                "id": "similar-1-id",
                "title": "Similar Product",
                "slug": "similar-product",
                "description": "Similar item",
                "status": "MODERATED",
                "category": {"id": self.category_id, "name": "Смартфоны"},
                "images": [{"url": "https://example.com/similar.jpg", "ordering": 0}],
                "skus": [{
                    "id": "sku-similar",
                    "name": "Variant",
                    "price": 9999000,
                    "discount": 1000000,
                    "image": "https://example.com/similar.jpg",
                    "active_quantity": 10,
                }],
            }]
            return (200, {"items": items, "total_count": 1, "limit": 8, "offset": 0})

        mock_b2b_get.side_effect = side_effect

        response = self.client.get(f"/api/v1/catalog/products/{self.product_id}/similar")

        self.assertEqual(response.status_code, 200)
        similar = response.data["items"][0]
        # min_price should be computed from sku price - discount
        self.assertEqual(similar["min_price"], 8999000)
        self.assertTrue(similar["has_stock"])
