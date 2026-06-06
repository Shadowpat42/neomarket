from unittest.mock import patch, Mock
from django.test import TestCase
from rest_framework.test import APIClient


PRODUCT_ID = "bc3fc1b9-873a-4651-9483-7249bd5173df"


class ProductCardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = f"/api/v1/products/{PRODUCT_ID}"

    @patch("catalog.views.requests.get")
    def test_product_card_returns_full_data_with_skus(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "id": PRODUCT_ID,
                    "title": "iPhone 15 Pro Max",
                    "description": "Флагман Apple",
                    "images": [
                        {
                            "url": "https://example.com/iphone.jpg",
                            "ordering": 0,
                        }
                    ],
                    "characteristics": [
                        {
                            "name": "Бренд",
                            "value": "Apple",
                        }
                    ],
                    "skus": [
                        {
                            "id": "62fbcabb-be0e-479e-a33b-b848c75da7e0",
                            "name": "256GB Black",
                            "price": 12999000,
                            "discount": 0,
                            "image": "https://example.com/iphone-black.jpg",
                            "active_quantity": 5,
                            "cost_price": 10000000,
                            "reserved_quantity": 0,
                            "characteristics": [
                                {
                                    "name": "Цвет",
                                    "value": "Чёрный",
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        mock_get.return_value = mock_response

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "iPhone 15 Pro Max")
        self.assertEqual(len(response.data["skus"]), 1)
        self.assertEqual(response.data["skus"][0]["price"], 12999000)
        self.assertTrue(response.data["skus"][0]["in_stock"])

    @patch("catalog.views.requests.get")
    def test_cost_price_absent_in_response(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "id": PRODUCT_ID,
                    "title": "iPhone 15 Pro Max",
                    "description": "Флагман Apple",
                    "images": [],
                    "characteristics": [],
                    "skus": [
                        {
                            "id": "62fbcabb-be0e-479e-a33b-b848c75da7e0",
                            "name": "256GB Black",
                            "price": 12999000,
                            "discount": 0,
                            "image": "https://example.com/iphone-black.jpg",
                            "active_quantity": 5,
                            "cost_price": 10000000,
                            "reserved_quantity": 0,
                            "characteristics": [],
                        }
                    ],
                }
            ]
        }
        mock_get.return_value = mock_response

        response = self.client.get(self.url)

        sku = response.data["skus"][0]

        self.assertNotIn("cost_price", sku)
        self.assertNotIn("reserved_quantity", sku)

    @patch("catalog.views.requests.get")
    def test_blocked_product_returns_404(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": []
        }
        mock_get.return_value = mock_response

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "PRODUCT_NOT_FOUND")

    @patch("catalog.views.requests.get")
    def test_sku_without_stock_is_shown_as_unavailable(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "id": PRODUCT_ID,
                    "title": "iPhone 15 Pro Max",
                    "description": "Флагман Apple",
                    "images": [],
                    "characteristics": [],
                    "skus": [
                        {
                            "id": "62fbcabb-be0e-479e-a33b-b848c75da7e0",
                            "name": "256GB Black",
                            "price": 12999000,
                            "discount": 0,
                            "image": "https://example.com/iphone-black.jpg",
                            "active_quantity": 0,
                            "characteristics": [],
                        }
                    ],
                }
            ]
        }
        mock_get.return_value = mock_response

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["skus"][0]["in_stock"])