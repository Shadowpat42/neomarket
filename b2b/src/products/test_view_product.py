import uuid

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import (
    Product,
    Category,
    Image,
    Characteristic,
    BlockingReason,
    ProductFieldReport,
)
from skus.models import SKU, SKUImage, SKUCharacteristic
from shared_models.models import BaseProductStatus


User = get_user_model()


class ViewProductTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="seller@test.com",
            password="12345678",
            first_name="Danil",
            last_name="Babikov",
            company_name="NeoMarket",
            phone="+79999999999",
        )
        self.another_user = User.objects.create_user(
            email="another@test.com",
            password="12345678",
            first_name="Ivan",
            last_name="Ivanov",
            company_name="AnotherCompany",
            phone="+78888888888",
        )
        self.category = Category.objects.create(name="iOS")
        self.client.force_authenticate(user=self.user)

    def _product_url(self, product_id):
        return f"/api/v1/products/{product_id}/"

    def _create_moderated_product_with_sku(self):
        product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="iPhone 15 Pro Max",
            description="Флагманский смартфон Apple",
            status=BaseProductStatus.MODERATED,
            slug="iphone-15-pro-max",
            deleted=False,
        )
        Image.objects.create(
            product=product,
            url="https://example.com/front.jpg",
            ordering=0,
        )
        Characteristic.objects.create(
            product=product, name="Бренд", value="Apple"
        )
        sku = SKU.objects.create(
            product=product,
            name="256GB Black",
            price=12999000,
            cost_price=9500000,
            discount=0,
            stock_quantity=12,
            reserved_quantity=2,
        )
        SKUImage.objects.create(
            sku=sku,
            url="https://example.com/black-256.jpg",
            ordering=0,
        )
        SKUCharacteristic.objects.create(
            sku=sku, name="Цвет", value="Чёрный"
        )
        return product, sku

    def _create_blocked_product_with_reports(self):
        reason = BlockingReason.objects.create(
            title="Описание не соответствует товару",
        )
        product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="Levi's 501",
            description="Джинсы",
            status=BaseProductStatus.BLOCKED,
            slug="levis-501",
            deleted=False,
            blocking_reason_id=reason.id,
            moderator_comment="Несоответствие описания и фотографий",
        )
        Image.objects.create(
            product=product,
            url="https://example.com/levis.jpg",
            ordering=0,
        )
        sku = SKU.objects.create(
            product=product,
            name="Размер 32",
            price=899000,
            cost_price=450000,
            discount=0,
        )
        SKUImage.objects.create(
            sku=sku,
            url="https://example.com/levis-32.jpg",
            ordering=0,
        )
        ProductFieldReport.objects.create(
            product=product,
            field_name="description",
            sku_id=None,
            comment="В описании указан другой материал",
        )
        ProductFieldReport.objects.create(
            product=product,
            field_name="sku_image",
            sku_id=sku.id,
            comment="Фото SKU не соответствует цвету",
        )
        return product, reason, sku

    def test_get_moderated_product_returns_full_payload(self):
        product, sku = self._create_moderated_product_with_sku()

        response = self.client.get(self._product_url(product.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "MODERATED")
        self.assertFalse(response.data["blocked"])
        self.assertIsNone(response.data["blocking_reason"])
        self.assertEqual(response.data["field_reports"], [])
        self.assertEqual(response.data["category"]["name"], "iOS")
        self.assertEqual(len(response.data["skus"]), 1)
        self.assertEqual(response.data["skus"][0]["id"], str(sku.id))
        self.assertEqual(response.data["skus"][0]["cost_price"], 9500000)
        self.assertEqual(response.data["skus"][0]["reserved_quantity"], 2)
        self.assertEqual(response.data["skus"][0]["active_quantity"], 10)
        self.assertIn("image", response.data["skus"][0])

    def test_get_blocked_product_returns_blocking_reason_and_field_reports(self):
        product, reason, _sku = self._create_blocked_product_with_reports()

        response = self.client.get(self._product_url(product.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "BLOCKED")
        self.assertTrue(response.data["blocked"])
        self.assertIsNotNone(response.data["blocking_reason"])
        self.assertEqual(
            response.data["blocking_reason"]["title"], reason.title
        )
        self.assertEqual(
            response.data["blocking_reason"]["comment"],
            "Несоответствие описания и фотографий",
        )
        self.assertEqual(len(response.data["field_reports"]), 2)
        field_names = {r["field_name"] for r in response.data["field_reports"]}
        self.assertIn("description", field_names)
        self.assertIn("sku_image", field_names)

    def test_get_others_product_returns_404(self):
        product, _ = self._create_moderated_product_with_sku()

        self.client.force_authenticate(user=self.another_user)
        response = self.client.get(self._product_url(product.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "NOT_FOUND")
        self.assertEqual(response.data["message"], "Product not found")

    def test_get_nonexistent_returns_404(self):
        response = self.client.get(self._product_url(uuid.uuid4()))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["code"], "NOT_FOUND")
        self.assertEqual(response.data["message"], "Product not found")
