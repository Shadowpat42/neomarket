import uuid

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Image, Product
from shared_models.models import BaseProductStatus
from skus.models import SKU, SKUImage

User = get_user_model()

CATALOG_URL = "/api/v1/public/products/"
SERVICE_KEY = "test-b2c-key"


def _auth_headers():
    return {"HTTP_X_SERVICE_KEY": SERVICE_KEY}


@override_settings(B2C_SERVICE_KEY=SERVICE_KEY)
class CatalogTests(APITestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            email="seller@test.com",
            password="12345678",
            first_name="Seller",
            last_name="One",
            company_name="Shop",
            phone="+79000000001",
        )
        self.category = Category.objects.create(name="Electronics")

    def _make_product(self, *, title="Product", prod_status=BaseProductStatus.MODERATED,
                      deleted=False, stock=10, reserved=0):
        p = Product.objects.create(
            seller_id=self.seller.id,
            category=self.category,
            title=title,
            description="Test description",
            status=prod_status,
            slug=title.lower().replace(" ", "-"),
            deleted=deleted,
        )
        Image.objects.create(product=p, url="https://example.com/img.jpg", ordering=0)
        sku = SKU.objects.create(
            product=p, name="default", price=100_00,
            cost_price=50_00, discount=0,
            stock_quantity=stock, reserved_quantity=reserved,
        )
        SKUImage.objects.create(sku=sku, url="https://example.com/sku.jpg", ordering=0)
        return p, sku

    # ── happy paths ──────────────────────────────────────────────────────────

    def test_catalog_returns_moderated_in_stock_products(self):
        visible, _ = self._make_product(title="Visible")
        self._make_product(title="No stock", stock=0)              # active_qty=0
        self._make_product(title="On mod", prod_status=BaseProductStatus.ON_MODERATION)
        self._make_product(title="Deleted", deleted=True)

        response = self.client.get(CATALOG_URL, **_auth_headers())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["items"]}
        self.assertIn(str(visible.id), ids)
        self.assertEqual(len(ids), 1)
        self.assertEqual(response.data["total_count"], 1)

    def test_batch_ids_returns_visible_subset(self):
        p1, _ = self._make_product(title="Product 1")
        p2, _ = self._make_product(title="Product 2")
        blocked, _ = self._make_product(
            title="Blocked", prod_status="HARD_BLOCKED"
        )

        ids_param = f"{p1.id},{p2.id},{blocked.id},{uuid.uuid4()}"
        response = self.client.get(
            CATALOG_URL, {"ids": ids_param}, **_auth_headers()
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data["items"]}
        self.assertIn(str(p1.id), returned_ids)
        self.assertIn(str(p2.id), returned_ids)
        self.assertNotIn(str(blocked.id), returned_ids)
        self.assertEqual(len(returned_ids), 2)

    # ── unhappy paths ─────────────────────────────────────────────────────────

    def test_catalog_excludes_hard_blocked(self):
        self._make_product(title="Visible")
        hard_blocked, _ = self._make_product(
            title="Hard Blocked", prod_status="HARD_BLOCKED"
        )

        response = self.client.get(CATALOG_URL, **_auth_headers())

        returned_ids = {item["id"] for item in response.data["items"]}
        self.assertNotIn(str(hard_blocked.id), returned_ids)

    def test_catalog_missing_service_key_returns_401(self):
        response = self.client.get(CATALOG_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["code"], "UNAUTHORIZED")

    def test_catalog_response_has_no_cost_price(self):
        self._make_product(title="iPhone")

        response = self.client.get(CATALOG_URL, **_auth_headers())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["items"]), 1)
        product_data = response.data["items"][0]
        self.assertIn("skus", product_data)
        self.assertGreater(len(product_data["skus"]), 0)
        sku_data = product_data["skus"][0]
        self.assertNotIn("cost_price", sku_data)
        self.assertNotIn("reserved_quantity", sku_data)
        self.assertIn("active_quantity", sku_data)
        self.assertIn("price", sku_data)
        self.assertIn("discount", sku_data)
