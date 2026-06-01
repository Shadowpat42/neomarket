import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Category, Product
from shared_models.models import BaseProductStatus


User = get_user_model()


@patch("skus.serializers.send_product_event")
class CreateSKUTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="seller@test.com",
            password="12345678",
            first_name="Danil",
            last_name="Babikov",
            company_name="NeoMarket",
            phone="+79999999999",
        )
        self.other_user = User.objects.create_user(
            email="other@test.com",
            password="12345678",
            first_name="Other",
            last_name="Seller",
            company_name="OtherCo",
            phone="+78888888888",
        )
        self.category = Category.objects.create(name="Phones")
        self.own_product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="My Phone",
            description="Mine",
        )
        self.foreign_product = Product.objects.create(
            seller_id=self.other_user.id,
            category=self.category,
            title="Foreign Phone",
            description="Not mine",
        )
        self.hard_blocked_product = Product.objects.create(
            seller_id=self.user.id,
            category=self.category,
            title="Blocked Phone",
            description="Hard blocked",
            status=BaseProductStatus.HARD_BLOCKED,
        )
        self.client.force_authenticate(user=self.user)
        self.url = "/api/v1/skus"

    def valid_payload(self, product_id=None, **overrides):
        payload = {
            "product_id": str(product_id or self.own_product.id),
            "name": "256GB Black",
            "price": 12999000,
            "cost_price": 9500000,
            "discount": 0,
            "image": "/s3/iphone15-black-256.jpg",
            "characteristics": [
                {"name": "Цвет", "value": "Чёрный"},
                {"name": "Объём памяти", "value": "256 ГБ"},
            ],
        }
        payload.update(overrides)
        return payload

    def test_first_sku_transitions_product_to_on_moderation(self, mock_send_event):
        response = self.client.post(self.url, self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.own_product.refresh_from_db()
        self.assertEqual(self.own_product.status, BaseProductStatus.ON_MODERATION)

    def test_first_sku_emits_created_event_to_moderation(self, mock_send_event):
        response = self.client.post(self.url, self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_send_event.assert_called_once()

        product_arg, event_type = mock_send_event.call_args[0]
        self.assertEqual(product_arg.id, self.own_product.id)
        self.assertEqual(event_type, "CREATED")

    @patch("skus.moderation.urllib.request.urlopen")
    def test_created_event_payload_fields(self, mock_urlopen, mock_send_event):
        from skus.moderation import send_product_event

        self.own_product.status = BaseProductStatus.ON_MODERATION
        self.own_product.save()

        fixed_key = uuid.UUID("d1e2f3a4-b5c6-7890-abcd-ef1234567890")
        with patch("skus.moderation.uuid.uuid4", return_value=fixed_key):
            payload = send_product_event(self.own_product, "CREATED")

        self.assertEqual(payload["event"], "CREATED")
        self.assertEqual(payload["product_id"], str(self.own_product.id))
        self.assertEqual(payload["seller_id"], str(self.user.id))
        self.assertEqual(payload["idempotency_key"], str(fixed_key))
        self.assertTrue(payload["date"].endswith("Z"))
        mock_urlopen.assert_called_once()

    def test_second_sku_no_state_change(self, mock_send_event):
        first_response = self.client.post(self.url, self.valid_payload(), format="json")
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        self.own_product.refresh_from_db()
        self.assertEqual(self.own_product.status, BaseProductStatus.ON_MODERATION)
        mock_send_event.reset_mock()

        second_response = self.client.post(
            self.url,
            self.valid_payload(name="512GB White", image="/s3/iphone15-white-512.jpg"),
            format="json",
        )

        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.own_product.refresh_from_db()
        self.assertEqual(self.own_product.status, BaseProductStatus.ON_MODERATION)
        mock_send_event.assert_not_called()

    def test_add_sku_to_hard_blocked_returns_403(self, mock_send_event):
        response = self.client.post(
            self.url,
            self.valid_payload(product_id=self.hard_blocked_product.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "FORBIDDEN")
        self.assertEqual(
            response.data["message"],
            "Cannot add SKU to hard-blocked product",
        )
        mock_send_event.assert_not_called()

    def test_missing_image_returns_400(self, mock_send_event):
        payload = self.valid_payload()
        payload.pop("image")

        response = self.client.post(self.url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "INVALID_REQUEST")
        self.assertEqual(response.data["message"], "image is required")
        mock_send_event.assert_not_called()

    def test_create_sku_for_foreign_product_returns_403(self, mock_send_event):
        response = self.client.post(
            self.url,
            self.valid_payload(product_id=self.foreign_product.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "FORBIDDEN")
        mock_send_event.assert_not_called()

    def test_create_sku_response_shape(self, mock_send_event):
        response = self.client.post(self.url, self.valid_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data
        self.assertEqual(data["name"], "256GB Black")
        self.assertEqual(data["price"], 12999000)
        self.assertEqual(data["cost_price"], 9500000)
        self.assertEqual(data["discount"], 0)
        self.assertEqual(data["image"], "/s3/iphone15-black-256.jpg")
        self.assertEqual(data["active_quantity"], 0)
        self.assertEqual(data["reserved_quantity"], 0)
        self.assertEqual(len(data["characteristics"]), 2)

    def test_moderated_product_add_sku_triggers_edited_event(self, mock_send_event):
        self.own_product.status = BaseProductStatus.MODERATED
        self.own_product.save()

        existing_sku_payload = self.valid_payload(name="128GB Silver")
        first = self.client.post(self.url, existing_sku_payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        self.own_product.refresh_from_db()
        self.assertEqual(self.own_product.status, BaseProductStatus.ON_MODERATION)
        mock_send_event.assert_called_once_with(self.own_product, "EDITED")
