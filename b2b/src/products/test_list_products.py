"""
US-B2B-11: список товаров продавца.

Сценарии:
  list_returns_only_own_products
  idor_query_param_seller_id_ignored
  deleted_products_visible_with_deleted_flag
  status_filter_works_correctly
  search_by_title_case_insensitive
"""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Image, Product
from shared_models.models import BaseProductStatus
from skus.models import SKU, SKUImage

User = get_user_model()

URL = "/api/v1/products/"


def _make_user(email, phone):
    return User.objects.create_user(
        email=email,
        password="pass1234",
        first_name="Test",
        last_name="User",
        company_name="TestCo",
        phone=phone,
    )


class ProductListTests(APITestCase):

    def setUp(self):
        self.seller = _make_user("seller@test.com", "+79111000011")
        self.other = _make_user("other@test.com", "+79111000012")
        self.category = Category.objects.create(name="Electronics")
        self.client.force_authenticate(user=self.seller)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _make_product(
        self,
        title="iPhone 15",
        seller=None,
        st=BaseProductStatus.MODERATED,
        deleted=False,
    ):
        seller = seller or self.seller
        product = Product.objects.create(
            seller_id=seller.id,
            category=self.category,
            title=title,
            description="Desc",
            status=st,
            deleted=deleted,
        )
        Image.objects.create(
            product=product,
            url="https://cdn.example.com/img.jpg",
            ordering=0,
        )
        return product

    def _make_sku(self, product, stock=5, reserved=2):
        sku = SKU.objects.create(
            product=product,
            name="Variant",
            price=10_000_00,
            cost_price=7_000_00,
            stock_quantity=stock,
            reserved_quantity=reserved,
        )
        SKUImage.objects.create(sku=sku, url="https://cdn.example.com/sku.jpg", ordering=0)
        return sku

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_list_returns_only_own_products(self):
        """
        GET /api/v1/products returns ONLY products owned by the authenticated seller.
        Products of other sellers must be absent.
        """
        own = self._make_product(title="Own product")
        self._make_product(title="Other's product", seller=self.other)

        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [item["id"] for item in resp.data["items"]]

        self.assertIn(str(own.id), ids)
        # Other seller's product must NOT appear
        other_products = Product.objects.filter(seller_id=self.other.id)
        for p in other_products:
            self.assertNotIn(str(p.id), ids)

        # Response shape
        self.assertIn("total_count", resp.data)
        self.assertIn("limit", resp.data)
        self.assertIn("offset", resp.data)

    def test_idor_query_param_seller_id_ignored(self):
        """
        ?seller_id=<other_seller_id> in query must be silently ignored.
        The response must still contain only the authenticated seller's products.
        """
        own = self._make_product(title="Mine")
        other = self._make_product(title="Not mine", seller=self.other)

        resp = self.client.get(URL, {"seller_id": str(self.other.id)})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        ids = [item["id"] for item in resp.data["items"]]
        self.assertIn(str(own.id), ids)
        self.assertNotIn(str(other.id), ids)

    def test_deleted_products_visible_with_deleted_flag(self):
        """
        Deleted products are excluded by default.
        With include_deleted=true they appear in the list.
        """
        active = self._make_product(title="Active", deleted=False)
        deleted = self._make_product(title="Deleted", deleted=True)

        # Default: deleted product must be absent
        resp_default = self.client.get(URL)
        ids_default = [item["id"] for item in resp_default.data["items"]]
        self.assertIn(str(active.id), ids_default)
        self.assertNotIn(str(deleted.id), ids_default)

        # With include_deleted=true: both visible
        resp_with = self.client.get(URL, {"include_deleted": "true"})
        ids_with = [item["id"] for item in resp_with.data["items"]]
        self.assertIn(str(active.id), ids_with)
        self.assertIn(str(deleted.id), ids_with)

    def test_status_filter_works_correctly(self):
        """
        ?status=BLOCKED returns only BLOCKED products; MODERATED are excluded.
        """
        moderated = self._make_product(title="Moderated", st=BaseProductStatus.MODERATED)
        blocked = self._make_product(title="Blocked", st=BaseProductStatus.BLOCKED)

        resp = self.client.get(URL, {"status": "BLOCKED"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        ids = [item["id"] for item in resp.data["items"]]
        self.assertIn(str(blocked.id), ids)
        self.assertNotIn(str(moderated.id), ids)

    def test_search_by_title_case_insensitive(self):
        """
        ?search=IPHONE matches titles with 'iphone' (any case).
        """
        iphone = self._make_product(title="iPhone 15 Pro")
        samsung = self._make_product(title="Samsung Galaxy S24")

        for query in ("iphone", "IPHONE", "Iphone", "iPHONE"):
            with self.subTest(query=query):
                resp = self.client.get(URL, {"search": query})
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                ids = [item["id"] for item in resp.data["items"]]
                self.assertIn(str(iphone.id), ids, f"Expected iphone for query {query!r}")
                self.assertNotIn(str(samsung.id), ids)

    def test_response_includes_skus_count_and_active_quantity(self):
        """
        Each item exposes skus_count and total_active_quantity.
        """
        product = self._make_product()
        self._make_sku(product, stock=10, reserved=3)   # active = 7
        self._make_sku(product, stock=5, reserved=5)    # active = 0

        resp = self.client.get(URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        item = next(i for i in resp.data["items"] if i["id"] == str(product.id))
        self.assertEqual(item["skus_count"], 2)
        self.assertEqual(item["total_active_quantity"], 7)
