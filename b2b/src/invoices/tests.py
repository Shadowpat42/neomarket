"""
US-B2B-06: создание накладной на поступление товара.

Сценарии:
  create_invoice_with_moderated_sku_returns_201
  empty_items_returns_400
  non_moderated_sku_returns_400
  others_sku_returns_403
"""
import uuid

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Image, Product
from shared_models.models import BaseProductStatus
from skus.models import SKU, SKUImage

User = get_user_model()

URL = "/api/v1/invoices"


def _make_user(email, phone):
    return User.objects.create_user(
        email=email,
        password="pass1234",
        first_name="Test",
        last_name="User",
        company_name="TestCo",
        phone=phone,
    )


class InvoiceCreateTests(APITestCase):

    def setUp(self):
        self.seller = _make_user("seller@test.com", "+79111000001")
        self.other = _make_user("other@test.com", "+79111000002")
        self.category = Category.objects.create(name="Phones")
        self.client.force_authenticate(user=self.seller)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _make_product(self, seller=None, st=BaseProductStatus.MODERATED):
        seller = seller or self.seller
        product = Product.objects.create(
            seller_id=seller.id,
            category=self.category,
            title="iPhone 15",
            description="Flagship",
            status=st,
        )
        Image.objects.create(
            product=product,
            url="https://cdn.example.com/img.jpg",
            ordering=0,
        )
        return product

    def _make_sku(self, product):
        sku = SKU.objects.create(
            product=product,
            name="128GB Black",
            price=100_000_00,
            cost_price=70_000_00,
            stock_quantity=0,
        )
        SKUImage.objects.create(sku=sku, url="https://cdn.example.com/sku.jpg", ordering=0)
        return sku

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_create_invoice_with_moderated_sku_returns_201(self):
        """
        Happy path: POST /api/v1/invoices with a valid MODERATED SKU.
        Response: 201, status=CREATED, items contain sku_id and quantity.
        """
        product = self._make_product(st=BaseProductStatus.MODERATED)
        sku = self._make_sku(product)

        payload = {"items": [{"sku_id": str(sku.id), "quantity": 10}]}
        resp = self.client.post(URL, payload, format="json")

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], "CREATED")
        self.assertEqual(str(resp.data["seller_id"]), str(self.seller.id))
        self.assertEqual(len(resp.data["items"]), 1)

        item = resp.data["items"][0]
        self.assertEqual(str(item["sku_id"]), str(sku.id))
        self.assertEqual(item["quantity"], 10)
        self.assertIsNone(item["accepted_quantity"])

    def test_empty_items_returns_400(self):
        """
        POST with items=[] → 400 INVALID_REQUEST.
        """
        resp = self.client.post(URL, {"items": []}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data["code"], "INVALID_REQUEST")

    def test_non_moderated_sku_returns_400(self):
        """
        POST with a SKU whose parent product is not MODERATED → 400 INVALID_REQUEST.
        """
        for bad_status in (
            BaseProductStatus.CREATED,
            BaseProductStatus.ON_MODERATION,
            BaseProductStatus.BLOCKED,
            BaseProductStatus.HARD_BLOCKED,
        ):
            with self.subTest(product_status=bad_status):
                product = self._make_product(st=bad_status)
                sku = self._make_sku(product)

                resp = self.client.post(
                    URL,
                    {"items": [{"sku_id": str(sku.id), "quantity": 5}]},
                    format="json",
                )
                self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(resp.data["code"], "INVALID_REQUEST")

    def test_others_sku_returns_403(self):
        """
        POST with a SKU belonging to another seller → 403 NOT_OWNER.
        """
        other_product = self._make_product(seller=self.other, st=BaseProductStatus.MODERATED)
        other_sku = self._make_sku(other_product)

        resp = self.client.post(
            URL,
            {"items": [{"sku_id": str(other_sku.id), "quantity": 3}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data["code"], "NOT_OWNER")
