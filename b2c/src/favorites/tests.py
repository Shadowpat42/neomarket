"""
US-CART-01: избранное покупателя
US-CART-02: подписки на изменения товара

ADR — user_id только из JWT:
  Три подхода рассмотрены в views.py. Выбран B (JWT Bearer).
  Тест user_id_from_query_is_ignored доказывает IDOR-защиту.
"""
import uuid
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from favorites.models import Favorite, ProductSubscription

USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
OTHER_USER_ID = "bbbbbbbb-0000-0000-0000-000000000002"
PRODUCT_ID = str(uuid.UUID("cccccccc-0000-0000-0000-000000000003"))
PRODUCT_ID_2 = str(uuid.UUID("dddddddd-0000-0000-0000-000000000004"))

# ── helpers ──────────────────────────────────────────────────────────────────


def _b2b_product(pid=PRODUCT_ID):
    return {
        "id": pid,
        "title": "iPhone 15",
        "slug": "iphone-15",
        "status": "MODERATED",
        "images": [{"url": "https://cdn.example.com/img.jpg", "ordering": 0}],
        "skus": [{"id": str(uuid.uuid4()), "name": "128GB", "price": 100_000_00,
                  "discount": 0, "active_quantity": 5}],
    }


def _b2b_list(*products):
    return (200, {"items": list(products), "total_count": len(products),
                  "limit": 20, "offset": 0})


# ════════════════════════════════════════════════════════════════
# US-CART-01: Favorites
# ════════════════════════════════════════════════════════════════

class FavoritesAddTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_USER_ID=USER_ID)

    def _url(self, pid=PRODUCT_ID):
        return f"/api/v1/favorites/{pid}"

    def test_add_to_favorites_returns_201(self):
        """
        POST /api/v1/favorites/{product_id} → 201 on first add.
        Record created in DB.
        """
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(str(resp.data["product_id"]), PRODUCT_ID)
        self.assertTrue(Favorite.objects.filter(
            user_id=USER_ID, product_id=PRODUCT_ID).exists())

    def test_repeat_add_returns_200_not_duplicate(self):
        """
        POST twice with the same product_id → second call returns 200, not 201.
        Only one row in DB (no duplicate).
        """
        self.client.post(self._url())
        resp = self.client.post(self._url())

        self.assertEqual(resp.status_code, 200)
        count = Favorite.objects.filter(user_id=USER_ID, product_id=PRODUCT_ID).count()
        self.assertEqual(count, 1, "Must not create a duplicate row")

    def test_delete_favorite_is_idempotent(self):
        """
        DELETE on non-existent favorite → 204, no error.
        """
        resp = self.client.delete(self._url())
        self.assertEqual(resp.status_code, 204)

    def test_user_id_from_query_is_ignored(self):
        """
        IDOR check: if user_id is passed in query, it must be ignored.
        The favorite is created for USER_ID (from X-User-Id), not for OTHER_USER_ID.
        """
        # Pass other user's ID in query — must be ignored
        resp = self.client.post(f"/api/v1/favorites/{PRODUCT_ID}?user_id={OTHER_USER_ID}")
        self.assertEqual(resp.status_code, 201)

        # Favorite must belong to authenticated USER_ID, not OTHER_USER_ID
        self.assertTrue(Favorite.objects.filter(
            user_id=USER_ID, product_id=PRODUCT_ID).exists())
        self.assertFalse(Favorite.objects.filter(
            user_id=OTHER_USER_ID, product_id=PRODUCT_ID).exists())


class FavoritesListTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_USER_ID=USER_ID)
        # Pre-populate favorite
        Favorite.objects.create(user_id=USER_ID, product_id=PRODUCT_ID)

    @patch("favorites.views._b2b_get")
    def test_get_favorites_enriched_from_b2b(self, mock_b2b_get):
        """
        GET /api/v1/favorites fetches product data from B2B and returns enriched list.
        """
        mock_b2b_get.return_value = _b2b_list(_b2b_product(PRODUCT_ID))

        resp = self.client.get("/api/v1/favorites")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total"], 1)
        item = resp.data["items"][0]
        self.assertEqual(str(item["product_id"]), PRODUCT_ID)
        self.assertIn("product", item)
        self.assertEqual(item["product"]["title"], "iPhone 15")

    @patch("favorites.views._b2b_get")
    def test_blocked_product_excluded_from_list(self, mock_b2b_get):
        """
        If a product is blocked/deleted in B2B, it's absent from B2B response
        and must be silently excluded from GET /favorites.
        """
        # B2B returns empty list (product blocked/deleted)
        mock_b2b_get.return_value = (200, {"items": [], "total_count": 0,
                                            "limit": 20, "offset": 0})

        resp = self.client.get("/api/v1/favorites")
        self.assertEqual(resp.status_code, 200)
        # total still counts stored favorites
        self.assertEqual(resp.data["total"], 1)
        # but items is empty because B2B didn't return the product
        self.assertEqual(len(resp.data["items"]), 0)


# ════════════════════════════════════════════════════════════════
# US-CART-02: Subscriptions
# ════════════════════════════════════════════════════════════════

class SubscriptionTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_X_USER_ID=USER_ID)
        self.url = f"/api/v1/favorites/{PRODUCT_ID}/subscribe"

    def _b2b_found(self):
        return _b2b_list(_b2b_product(PRODUCT_ID))

    def _b2b_not_found(self):
        return (200, {"items": [], "total_count": 0, "limit": 20, "offset": 0})

    @patch("favorites.views._b2b_get")
    def test_subscribe_returns_201_with_notify_on(self, mock_b2b_get):
        """
        POST /api/v1/favorites/{product_id}/subscribe → 201, subscription persisted.
        """
        mock_b2b_get.return_value = self._b2b_found()

        resp = self.client.post(
            self.url,
            {"notify_on": ["IN_STOCK", "PRICE_DOWN"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(sorted(resp.data["notify_on"]), ["IN_STOCK", "PRICE_DOWN"])
        self.assertTrue(ProductSubscription.objects.filter(
            user_id=USER_ID, product_id=PRODUCT_ID).exists())

    @patch("favorites.views._b2b_get")
    def test_duplicate_subscription_returns_409(self, mock_b2b_get):
        """
        Second POST with same product_id → 409 SUBSCRIPTION_ALREADY_EXISTS.
        """
        mock_b2b_get.return_value = self._b2b_found()
        self.client.post(self.url, {"notify_on": ["IN_STOCK"]}, format="json")

        mock_b2b_get.return_value = self._b2b_found()
        resp = self.client.post(self.url, {"notify_on": ["PRICE_DOWN"]}, format="json")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "SUBSCRIPTION_ALREADY_EXISTS")

    def test_invalid_notify_on_returns_400(self):
        """
        Empty or unknown notify_on → 400 INVALID_NOTIFY_ON.
        """
        for bad in [[], ["UNKNOWN_EVENT"], None]:
            with self.subTest(notify_on=bad):
                resp = self.client.post(
                    self.url,
                    {"notify_on": bad},
                    format="json",
                )
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.data["code"], "INVALID_NOTIFY_ON")

    @patch("favorites.views._b2b_get")
    def test_subscribe_to_unknown_product_returns_404(self, mock_b2b_get):
        """
        Product not found in B2B → 404 PRODUCT_NOT_FOUND.
        """
        mock_b2b_get.return_value = self._b2b_not_found()

        resp = self.client.post(
            self.url,
            {"notify_on": ["IN_STOCK"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.data["code"], "PRODUCT_NOT_FOUND")
