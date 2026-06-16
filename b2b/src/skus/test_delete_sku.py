"""
US-B2B-12: удаление отдельного варианта (SKU).

Порядок проверок: HARD_BLOCKED → reserved_quantity → удаление + side-effects.

Сценарии:
  delete_sku_succeeds
  delete_sku_with_active_reserves_returns_409
  last_sku_on_moderation_transitions_product_to_created
  delete_sku_hard_blocked_product_returns_403
  sku_out_of_stock_event_on_moderated_product
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


def _make_user(email, phone):
    return User.objects.create_user(
        email=email,
        password="pass1234",
        first_name="Test",
        last_name="User",
        company_name="TestCo",
        phone=phone,
    )


class DeleteSKUTests(APITestCase):

    def setUp(self):
        self.seller = _make_user("seller@sku.test", "+79300000001")
        self.other = _make_user("other@sku.test", "+79300000002")
        self.category = Category.objects.create(name="Electronics")
        self.client.force_authenticate(user=self.seller)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _make_product(self, st=BaseProductStatus.MODERATED, seller=None):
        seller = seller or self.seller
        product = Product.objects.create(
            seller_id=seller.id,
            category=self.category,
            title="iPhone 15",
            description="Desc",
            status=st,
        )
        Image.objects.create(
            product=product,
            url="https://cdn.example.com/img.jpg",
            ordering=0,
        )
        return product

    def _make_sku(self, product, stock=10, reserved=0):
        sku = SKU.objects.create(
            product=product,
            name="128GB Black",
            price=100_000_00,
            cost_price=70_000_00,
            stock_quantity=stock,
            reserved_quantity=reserved,
        )
        SKUImage.objects.create(sku=sku, url="https://cdn.example.com/sku.jpg", ordering=0)
        return sku

    def _url(self, sku):
        return f"/api/v1/skus/{sku.id}"

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_delete_sku_succeeds(self):
        """
        DELETE /api/v1/skus/{id}: happy path — SKU is removed, returns 204.
        """
        product = self._make_product()
        sku = self._make_sku(product, stock=5, reserved=0)
        sku_id = sku.id

        resp = self.client.delete(self._url(sku))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SKU.objects.filter(id=sku_id).exists())

    def test_delete_sku_with_active_reserves_returns_409(self):
        """
        DELETE on a SKU with reserved_quantity > 0 → 409 CONFLICT.
        """
        product = self._make_product()
        sku = self._make_sku(product, stock=10, reserved=3)

        resp = self.client.delete(self._url(sku))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data["code"], "CONFLICT")
        # SKU must still exist
        self.assertTrue(SKU.objects.filter(id=sku.id).exists())

    def test_last_sku_on_moderation_transitions_product_to_created(self):
        """
        Deleting the last SKU from an ON_MODERATION product:
        - product status → CREATED
        - PRODUCT_DELETED event sent to Moderation
        """
        product = self._make_product(st=BaseProductStatus.ON_MODERATION)
        sku = self._make_sku(product, stock=5, reserved=0)

        with patch("skus.views.send_product_moderation_event") as mock_send:
            resp = self.client.delete(self._url(sku))

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        product.refresh_from_db()
        self.assertEqual(product.status, BaseProductStatus.CREATED)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[1]["event_type"], "PRODUCT_DELETED")

    def test_delete_sku_hard_blocked_product_returns_403(self):
        """
        DELETE on a SKU whose parent product is HARD_BLOCKED → 403 FORBIDDEN.
        """
        product = self._make_product(st=BaseProductStatus.HARD_BLOCKED)
        sku = self._make_sku(product, stock=5, reserved=0)

        resp = self.client.delete(self._url(sku))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], "FORBIDDEN")
        # SKU must still exist
        self.assertTrue(SKU.objects.filter(id=sku.id).exists())

    def test_sku_out_of_stock_event_on_moderated_product(self):
        """
        DELETE on a SKU with active_quantity > 0 from a MODERATED product
        → SKU_OUT_OF_STOCK event sent to B2C.
        """
        product = self._make_product(st=BaseProductStatus.MODERATED)
        # stock=5, reserved=0 → active=5 > 0
        sku = self._make_sku(product, stock=5, reserved=0)

        with patch("skus.views.notify_sku_out_of_stock") as mock_notify:
            resp = self.client.delete(self._url(sku))

        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args[1]
        self.assertEqual(str(call_kwargs["sku_id"]), str(sku.id))
        self.assertEqual(str(call_kwargs["product_id"]), str(product.id))
