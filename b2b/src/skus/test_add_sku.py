import datetime
import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Product
from skus.models import SKU
from shared_models.models import BaseProductStatus


User = get_user_model()


class AddSkuTests(APITestCase):
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

        self.url = "/api/v1/skus"

    def _create_product(self, *, status_value=BaseProductStatus.CREATED):
        return Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="iPhone",
            description="Apple smartphone",
            status=status_value,
            slug="iphone",
            deleted=False,
        )

    def valid_payload(self, *, product_id, name="SKU", price=12999000, cost_price=9500000, image="https://example.com/1.jpg"):
        return {
            "product_id": str(product_id),
            "name": name,
            "price": price,
            "cost_price": cost_price,
            "discount": 0,
            "image": image,
            "characteristics": [
                {"name": "Цвет", "value": "Чёрный"},
            ],
        }

    @patch("skus.views.send_product_moderation_event")
    def test_first_sku_transitions_product_to_on_moderation(self, mock_send):
        product = self._create_product(status_value=BaseProductStatus.CREATED)
        payload = self.valid_payload(product_id=product.id, name="256GB Black")

        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        product.refresh_from_db()
        self.assertEqual(product.status, BaseProductStatus.ON_MODERATION)
        self.assertTrue(SKU.objects.filter(product_id=product.id).exists())

    @patch("skus.views.send_product_moderation_event")
    def test_first_sku_emits_created_event_to_moderation(self, mock_send):
        product = self._create_product(status_value=BaseProductStatus.CREATED)

        fixed_uuid = uuid.UUID("d1e2f3a4-b5c6-7890-abcd-ef1234567890")
        fixed_dt = datetime.datetime(
            2026, 3, 15, 14, 30, 0, 123000, tzinfo=datetime.timezone.utc
        )

        payload = self.valid_payload(product_id=product.id, name="256GB Black")
        with (
            patch("skus.views.uuid.uuid4", return_value=fixed_uuid),
            patch("skus.views.timezone.now", return_value=fixed_dt),
        ):
            response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        mock_send.assert_called_once_with(
            event_type="PRODUCT_CREATED",
            product_id=product.id,
            seller_id=product.seller_id,
            idempotency_key=fixed_uuid,
            occurred_at=fixed_dt,
        )

    @patch("skus.views.send_product_moderation_event")
    def test_second_sku_no_state_change(self, mock_send):
        product = self._create_product(status_value=BaseProductStatus.CREATED)

        first_payload = self.valid_payload(product_id=product.id, name="SKU-1")
        response1 = self.client.post(self.url, first_payload, format="json")
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        mock_send.assert_called_once()  # event CREATED for first SKU

        product.refresh_from_db()
        self.assertEqual(product.status, BaseProductStatus.ON_MODERATION)

        second_payload = self.valid_payload(product_id=product.id, name="SKU-2", price=19999000)
        response2 = self.client.post(self.url, second_payload, format="json")
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)

        product.refresh_from_db()
        self.assertEqual(product.status, BaseProductStatus.ON_MODERATION)
        self.assertEqual(mock_send.call_count, 1)

    def test_add_sku_to_hard_blocked_returns_403(self):
        product = self._create_product(status_value="HARD_BLOCKED")

        payload = self.valid_payload(product_id=product.id, name="SKU")
        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "FORBIDDEN")
        self.assertEqual(
            response.data["message"], "Cannot add SKU to hard-blocked product"
        )

    def test_missing_image_returns_400(self):
        product = self._create_product(status_value=BaseProductStatus.CREATED)

        payload = self.valid_payload(product_id=product.id, name="SKU")
        payload.pop("image")

        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "INVALID_REQUEST")
        self.assertEqual(response.data["message"], "image is required")

