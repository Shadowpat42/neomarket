"""
US-B2B-03: редактирование товара/SKU.

Сценарии:
  edit_moderated_product_returns_to_on_moderation
  edit_blocked_product_returns_to_on_moderation
  reserves_preserved_after_sku_edit
  edit_hard_blocked_returns_403
  edit_others_product_returns_403
"""
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Image, Product
from shared_models.models import BaseProductStatus
from skus.models import SKU, SKUImage

User = get_user_model()


def _make_user(email, **kwargs):
    defaults = dict(
        password="pass1234",
        first_name="Test",
        last_name="User",
        company_name="TestCo",
        phone="+79000000000",
    )
    defaults.update(kwargs)
    return User.objects.create_user(email=email, **defaults)


class EditProductTests(APITestCase):

    def setUp(self):
        self.seller = _make_user("seller@test.com", phone="+79111111111")
        self.other = _make_user("other@test.com", phone="+79222222222")
        self.category = Category.objects.create(name="Phones")
        self.client.force_authenticate(user=self.seller)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _make_product(self, st=BaseProductStatus.MODERATED):
        product = Product.objects.create(
            seller_id=self.seller.id,
            category=self.category,
            title="iPhone 15",
            description="Flagship",
            status=st,
        )
        Image.objects.create(product=product, url="https://cdn.example.com/img.jpg", ordering=0)
        return product

    def _make_sku(self, product, reserved=0):
        sku = SKU.objects.create(
            product=product,
            name="128GB Black",
            price=10000_00,
            cost_price=7000_00,
            stock_quantity=10,
            reserved_quantity=reserved,
        )
        SKUImage.objects.create(sku=sku, url="https://cdn.example.com/sku.jpg", ordering=0)
        return sku

    def _put_product_payload(self, title="iPhone 15 (updated)"):
        return {
            "title": title,
            "description": "Updated description",
            "category_id": str(self.category.id),
            "images": [{"url": "https://cdn.example.com/new.jpg", "ordering": 0}],
        }

    def _put_sku_payload(self):
        return {
            "name": "128GB Black (updated)",
            "price": 10500_00,
            "cost_price": 7500_00,
            "image": "https://cdn.example.com/sku-new.jpg",
        }

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_edit_moderated_product_returns_to_on_moderation(self):
        """
        PUT /api/v1/products/{id} on a MODERATED product:
        - status transitions to ON_MODERATION
        - PRODUCT_EDITED event is sent to Moderation
        """
        product = self._make_product(st=BaseProductStatus.MODERATED)

        with patch("products.views.send_product_moderation_event") as mock_send:
            resp = self.client.put(
                f"/api/v1/products/{product.id}/",
                self._put_product_payload(),
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.status, BaseProductStatus.ON_MODERATION)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[1]["event_type"], "PRODUCT_EDITED")

    def test_edit_blocked_product_returns_to_on_moderation(self):
        """
        PUT /api/v1/products/{id} on a BLOCKED product:
        - status transitions to ON_MODERATION
        - PRODUCT_EDITED event is sent
        """
        product = self._make_product(st=BaseProductStatus.BLOCKED)

        with patch("products.views.send_product_moderation_event") as mock_send:
            resp = self.client.put(
                f"/api/v1/products/{product.id}/",
                self._put_product_payload(title="iPhone 15 (fixed)"),
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.status, BaseProductStatus.ON_MODERATION)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[1]["event_type"], "PRODUCT_EDITED")

    def test_reserves_preserved_after_sku_edit(self):
        """
        PUT /api/v1/skus/{id}: reserved_quantity is never touched by edit.
        """
        product = self._make_product(st=BaseProductStatus.MODERATED)
        sku = self._make_sku(product, reserved=3)
        original_reserved = sku.reserved_quantity

        with patch("skus.views.send_product_moderation_event"):
            resp = self.client.put(
                f"/api/v1/skus/{sku.id}",
                self._put_sku_payload(),
                format="json",
            )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        sku.refresh_from_db()
        self.assertEqual(sku.reserved_quantity, original_reserved,
                         "reserved_quantity must not change after SKU edit")

    def test_edit_hard_blocked_returns_403(self):
        """
        Any PUT on a HARD_BLOCKED product (or SKU of such product) → 403 FORBIDDEN.
        """
        product = self._make_product(st=BaseProductStatus.HARD_BLOCKED)

        resp = self.client.put(
            f"/api/v1/products/{product.id}/",
            self._put_product_payload(),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], "FORBIDDEN")

        # SKU of HARD_BLOCKED product also forbidden
        sku = self._make_sku(product)
        resp_sku = self.client.put(
            f"/api/v1/skus/{sku.id}",
            self._put_sku_payload(),
            format="json",
        )
        self.assertEqual(resp_sku.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp_sku.data["code"], "FORBIDDEN")

    def test_edit_others_product_returns_403(self):
        """
        PUT /api/v1/products/{id} on another seller's product → 403 NOT_OWNER.
        """
        product = Product.objects.create(
            seller_id=self.other.id,
            category=self.category,
            title="Other's phone",
            description="Not mine",
            status=BaseProductStatus.MODERATED,
        )
        Image.objects.create(product=product, url="https://cdn.example.com/other.jpg", ordering=0)

        resp = self.client.put(
            f"/api/v1/products/{product.id}/",
            self._put_product_payload(),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], "NOT_OWNER")

        # SKU ownership check via parent product
        sku = self._make_sku(product)
        resp_sku = self.client.put(
            f"/api/v1/skus/{sku.id}",
            self._put_sku_payload(),
            format="json",
        )
        self.assertEqual(resp_sku.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp_sku.data["code"], "NOT_OWNER")
