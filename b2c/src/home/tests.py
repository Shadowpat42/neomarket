"""
US-CART-04: баннеры на главной
US-CART-05: подборки товаров на главной

Сценарии:
  active_banners_returned_sorted_by_priority
  no_active_banners_returns_200_empty
  click_on_unknown_banner_returns_400
  collections_list_returns_metadata_without_products
  collection_products_enriched_from_b2b
  unavailable_products_in_unavailable_ids
  unknown_collection_returns_404
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from home.models import Banner, Collection, CollectionProduct

PRODUCT_ID_1 = str(uuid.UUID("aaaaaaaa-0001-0000-0000-000000000001"))
PRODUCT_ID_2 = str(uuid.UUID("bbbbbbbb-0002-0000-0000-000000000002"))
PRODUCT_ID_3 = str(uuid.UUID("cccccccc-0003-0000-0000-000000000003"))


def _b2b_product(pid, title="Product"):
    return {
        "id": pid,
        "title": title,
        "slug": title.lower().replace(" ", "-"),
        "status": "MODERATED",
        "images": [],
        "skus": [],
    }


# ════════════════════════════════════════════════════════════════
# US-CART-04: Banners
# ════════════════════════════════════════════════════════════════

class BannerListTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        now = timezone.now()
        Banner.objects.create(
            title="Баннер 1", image_url="https://cdn/1.jpg",
            link="/cat/1", priority=10, is_active=True,
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
        )
        Banner.objects.create(
            title="Баннер 2", image_url="https://cdn/2.jpg",
            link="/cat/2", priority=5, is_active=True,
        )
        Banner.objects.create(
            title="Старый баннер", image_url="https://cdn/3.jpg",
            link="/cat/3", priority=1, is_active=True,
            end_at=now - timedelta(hours=1),  # expired
        )
        Banner.objects.create(
            title="Неактивный", image_url="https://cdn/4.jpg",
            link="/cat/4", priority=0, is_active=False,
        )

    def test_active_banners_returned_sorted_by_priority(self):
        """
        GET /api/v1/home/banners returns only active, in-schedule banners,
        sorted ascending by priority.
        """
        resp = self.client.get("/api/v1/home/banners")
        self.assertEqual(resp.status_code, 200)
        items = resp.data["items"]
        # 2 active in-schedule banners (Баннер 1 and Баннер 2), expired excluded
        self.assertEqual(len(items), 2)
        # Sorted by priority ascending
        priorities = [item["priority"] for item in items]
        self.assertEqual(priorities, sorted(priorities))
        # Inactive and expired must NOT appear
        titles = [item["title"] for item in items]
        self.assertNotIn("Старый баннер", titles)
        self.assertNotIn("Неактивный", titles)

    def test_no_active_banners_returns_200_empty(self):
        """
        When no banners are active, returns 200 with empty items list.
        """
        Banner.objects.all().update(is_active=False)
        resp = self.client.get("/api/v1/home/banners")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["items"], [])
        self.assertEqual(resp.data["total_count"], 0)


class BannerEventTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.banner = Banner.objects.create(
            title="Test Banner",
            image_url="https://cdn/test.jpg",
            link="/test",
            is_active=True,
        )

    def test_click_on_unknown_banner_returns_400(self):
        """
        POST /api/v1/banner-events with an unknown banner_id → 400 BANNER_NOT_FOUND.
        """
        unknown_id = str(uuid.uuid4())
        resp = self.client.post(
            "/api/v1/banner-events",
            {"events": [{"banner_id": unknown_id, "event_type": "click"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "BANNER_NOT_FOUND")

    def test_valid_banner_event_returns_200(self):
        """
        POST /api/v1/banner-events with valid banner_id → 200, event persisted.
        """
        resp = self.client.post(
            "/api/v1/banner-events",
            {"events": [{"banner_id": str(self.banner.id), "event_type": "impression"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["ok"])

    def test_empty_events_returns_400(self):
        """
        POST with empty events array → 400 EMPTY_EVENTS.
        """
        resp = self.client.post(
            "/api/v1/banner-events",
            {"events": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "EMPTY_EVENTS")


# ════════════════════════════════════════════════════════════════
# US-CART-05: Collections
# ════════════════════════════════════════════════════════════════

class CollectionsListTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.col1 = Collection.objects.create(
            title="Хиты продаж", priority=10, is_active=True
        )
        self.col2 = Collection.objects.create(
            title="Новинки", priority=5, is_active=True
        )
        Collection.objects.create(
            title="Неактивная", priority=1, is_active=False
        )
        # Add some products to col1
        for pid in [PRODUCT_ID_1, PRODUCT_ID_2]:
            CollectionProduct.objects.create(collection=self.col1, product_id=pid)

    def test_collections_list_returns_metadata_without_products(self):
        """
        GET /api/v1/main/collections returns collection metadata.
        Does NOT include product data (no products field in items).
        """
        resp = self.client.get("/api/v1/main/collections")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total_count"], 2)  # inactive excluded
        titles = [c["title"] for c in resp.data["items"]]
        self.assertIn("Хиты продаж", titles)
        self.assertIn("Новинки", titles)
        self.assertNotIn("Неактивная", titles)
        # No products inside items
        for item in resp.data["items"]:
            self.assertNotIn("products", item)


class CollectionProductsTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.col = Collection.objects.create(
            title="Хиты", priority=0, is_active=True
        )
        CollectionProduct.objects.create(collection=self.col, product_id=PRODUCT_ID_1, ordering=0)
        CollectionProduct.objects.create(collection=self.col, product_id=PRODUCT_ID_2, ordering=1)
        CollectionProduct.objects.create(collection=self.col, product_id=PRODUCT_ID_3, ordering=2)

    def _url(self, col_id=None):
        return f"/api/v1/collections/{col_id or self.col.id}/products"

    @patch("home.views._b2b_get")
    def test_collection_products_enriched_from_b2b(self, mock_b2b_get):
        """
        GET /api/v1/collections/{id}/products returns B2B-enriched product list.
        """
        mock_b2b_get.return_value = (
            200,
            {
                "items": [
                    _b2b_product(PRODUCT_ID_1, "iPhone 15"),
                    _b2b_product(PRODUCT_ID_2, "MacBook"),
                    _b2b_product(PRODUCT_ID_3, "AirPods"),
                ],
                "total_count": 3,
            },
        )
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["items"]), 3)
        self.assertEqual(resp.data["unavailable_ids"], [])

    @patch("home.views._b2b_get")
    def test_unavailable_products_in_unavailable_ids(self, mock_b2b_get):
        """
        Products absent from B2B response (deleted/blocked) appear in unavailable_ids,
        not in items.
        """
        # B2B only returns 1 of 3 products
        mock_b2b_get.return_value = (
            200,
            {"items": [_b2b_product(PRODUCT_ID_1)], "total_count": 1},
        )
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["items"]), 1)
        unavailable = resp.data["unavailable_ids"]
        self.assertIn(PRODUCT_ID_2, unavailable)
        self.assertIn(PRODUCT_ID_3, unavailable)
        self.assertNotIn(PRODUCT_ID_1, unavailable)

    def test_unknown_collection_returns_404(self):
        """
        GET /api/v1/collections/{unknown_id}/products → 404.
        """
        resp = self.client.get(self._url(col_id=uuid.uuid4()))
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data["code"], "NOT_FOUND")
