import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Product, Category, Image
from skus.models import SKU, SKUImage
from shared_models.models import BaseProductStatus
from unittest.mock import patch


User = get_user_model()


class CreateProductTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="seller@test.com",
            password="12345678",
            first_name="aaaaa",
            last_name="aaaaaaa",
            company_name="NeoMarket",
            phone="+79999999999"
        )

        self.another_user = User.objects.create_user(
            email="another@test.com",
            password="12345678",
            first_name="Ivan",
            last_name="Ivanov",
            company_name="AnotherCompany",
            phone="+78888888888"
        )

        self.category = Category.objects.create(
            name="iOS"
        )

        self.client.force_authenticate(user=self.user)

        self.url = "/api/v1/products/"

    def valid_payload(self):
        return {
            "title": "iPhone 15 Pro Max",
            "description": "Apple smartphone",
            "category_id": str(self.category.id),
            "images": [
                {
                    "url": "https://example.com/front.jpg",
                    "ordering": 0
                }
            ],
            "characteristics": [
                {
                    "name": "Бренд",
                    "value": "Apple"
                }
            ]
        }

    def test_create_product_returns_201_with_created_status(self):
        response = self.client.post(
            self.url,
            self.valid_payload(),
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        self.assertEqual(
            response.data["status"],
            "CREATED"
        )

        self.assertEqual(
            response.data["skus"],
            []
        )

        product = Product.objects.get(id=response.data["id"])

        self.assertEqual(product.status, "CREATED")

    def test_seller_id_taken_from_jwt(self):
        payload = self.valid_payload()

        payload["seller_id"] = str(self.another_user.id)

        response = self.client.post(
            self.url,
            payload,
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

        product = Product.objects.get(id=response.data["id"])

        self.assertEqual(
            str(product.seller_id),
            str(self.user.id)
        )

        self.assertNotEqual(
            str(product.seller_id),
            str(self.another_user.id)
        )

    def test_missing_images_returns_400(self):
        payload = self.valid_payload()

        payload.pop("images")

        response = self.client.post(
            self.url,
            payload,
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["code"],
            "INVALID_REQUEST"
        )

    def test_missing_category_returns_400(self):
        payload = {
            "title": "iPhone",
            "description": "Apple smartphone",
            "images": [
                {
                    "url": "/s3/front.jpg",
                    "ordering": 0
                }
            ]
        }

        response = self.client.post(
            self.url,
            payload,
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["code"],
            "INVALID_REQUEST"
        )

    def test_invalid_category_id_returns_400(self):
        payload = {
            "title": "iPhone",
            "description": "Apple smartphone",
            "category_id": str(uuid.uuid4()),
            "images": [
                {
                    "url": "/s3/front.jpg",
                    "ordering": 0
                }
            ]
        }

        response = self.client.post(
            self.url,
            payload,
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["code"],
            "INVALID_REQUEST"
        )

        self.assertEqual(
            response.data["message"],
            "Category not found"
        )

    def test_invalid_category_uuid_returns_400(self):
        payload = {
            "title": "iPhone",
            "description": "Apple smartphone",
            "category_id": "not-uuid",
            "images": [
                {
                    "url": "/s3/front.jpg",
                    "ordering": 0
                }
            ]
        }

        response = self.client.post(
            self.url,
            payload,
            format="json"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["message"],
            "category_id must be a valid UUID"
        )


class DeleteProductTests(APITestCase):
    """B2B-4: Delete product with soft delete and events tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="seller@test.com",
            password="12345678",
            first_name="aaaaa",
            last_name="aaaaaa",
            company_name="NeoMarket",
            phone="+79999999999"
        )

        self.another_user = User.objects.create_user(
            email="another@test.com",
            password="12345678",
            first_name="Ivan",
            last_name="Ivanov",
            company_name="AnotherCompany",
            phone="+78888888888"
        )

        self.category = Category.objects.create(name="iOS")

        self.client.force_authenticate(user=self.user)

    def test_delete_sets_deleted_true(self):
        """B2B-4: Soft delete sets deleted=true in database."""
        product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="iPhone 15",
            description="Description",
            status=BaseProductStatus.MODERATED,
        )
        Image.objects.create(product=product, url="/s3/iphone.jpg", ordering=0)

        response = self.client.delete(f"/api/v1/products/{product.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        product.refresh_from_db()
        self.assertTrue(product.deleted)

    def test_delete_emits_event_to_moderation(self):
        """B2B-4: Delete sends DELETED event to Moderation."""
        product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="iPhone 15",
            description="Description",
            status=BaseProductStatus.MODERATED,
        )
        Image.objects.create(product=product, url="/s3/iphone.jpg", ordering=0)
        sku = SKU.objects.create(
            product=product,
            name="256GB Black",
            price=12999000,
            cost_price=9500000,
            stock_quantity=10,
        )
        SKUImage.objects.create(sku=sku, url="/s3/iphone-black.jpg", ordering=0)

        with patch("products.views.send_product_moderation_event") as mock_send:
            response = self.client.delete(f"/api/v1/products/{product.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        self.assertEqual(call_args[1]["event_type"], "DELETED")
        self.assertEqual(call_args[1]["product_id"], product.id)

    def test_delete_emits_product_deleted_to_b2c(self):
        """B2B-4: Delete sends PRODUCT_DELETED event to B2C with sku_ids."""
        product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="iPhone 15",
            description="Description",
            status=BaseProductStatus.MODERATED,
        )
        Image.objects.create(product=product, url="/s3/iphone.jpg", ordering=0)
        sku = SKU.objects.create(
            product=product,
            name="256GB Black",
            price=12999000,
            cost_price=9500000,
            stock_quantity=10,
        )
        SKUImage.objects.create(sku=sku, url="/s3/iphone-black.jpg", ordering=0)

        with patch("b2c_client.notify_product_deleted") as mock_notify:
            response = self.client.delete(f"/api/v1/products/{product.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_notify.assert_called_once()
        call_args = mock_notify.call_args
        self.assertEqual(call_args[1]["product_id"], product.id)
        self.assertIn(str(sku.id), call_args[1]["sku_ids"])

    def test_delete_already_deleted_returns_400(self):
        """B2B-4: Deleting already deleted product returns 400."""
        product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="iPhone 15",
            description="Description",
            status=BaseProductStatus.MODERATED,
            deleted=True,
        )
        Image.objects.create(product=product, url="/s3/iphone.jpg", ordering=0)

        response = self.client.delete(f"/api/v1/products/{product.id}/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "INVALID_REQUEST")

    def test_deleted_product_not_in_seller_list(self):
        """B2B-4: Deleted product is visible in seller list with deleted=true flag."""
        product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="iPhone 15",
            description="Description",
            status=BaseProductStatus.MODERATED,
            deleted=True,
        )
        Image.objects.create(product=product, url="/s3/iphone.jpg", ordering=0)

        response = self.client.get("/api/v1/products/my")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.data
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(product.id))
        self.assertTrue(items[0]["deleted"])

    def test_delete_others_product_returns_403(self):
        """B2B-4: Deleting another seller's product returns 403."""
        product = Product.objects.create(
            seller_id=self.another_user.id,
            category=self.category,
            title="iPhone 15",
            description="Description",
            status=BaseProductStatus.MODERATED,
        )
        Image.objects.create(product=product, url="/s3/iphone.jpg", ordering=0)

        response = self.client.delete(f"/api/v1/products/{product.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_hard_blocked_product_returns_403(self):
        """B2B-4: Deleting HARD_BLOCKED product returns 403."""
        product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="iPhone 15",
            description="Description",
            status=BaseProductStatus.HARD_BLOCKED,
        )
        Image.objects.create(product=product, url="/s3/iphone.jpg", ordering=0)

        response = self.client.delete(f"/api/v1/products/{product.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)