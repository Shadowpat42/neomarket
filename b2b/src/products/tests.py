import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Product, Category


User = get_user_model()


class CreateProductTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="seller@test.com",
            password="12345678",
            first_name="Danil",
            last_name="Babikov",
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