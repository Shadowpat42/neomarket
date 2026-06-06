import requests

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class ProductCardView(APIView):
    def get(self, request, product_id):
        try:
            response = requests.get(
                "http://127.0.0.1:8001/api/v1/public/products/",
                params={"ids": str(product_id)},
                headers={"X-Service-Key": "b2c_service_key"},
                timeout=5,
                proxies={"http": None, "https": None},
            )
        except requests.RequestException:
            return Response(
                {
                    "code": "B2B_UNAVAILABLE",
                    "message": "B2B сервис временно недоступен",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if response.status_code != 200:
            return Response(
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        data = response.json()

        if isinstance(data, dict):
            products = data.get("items", [])
        else:
            products = data

        if not products:
            return Response(
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        product = products[0]

        for sku in product.get("skus", []):
            sku.pop("cost_price", None)
            sku.pop("reserved_quantity", None)
            sku["in_stock"] = sku.get("active_quantity", 0) > 0

        return Response(product, status=status.HTTP_200_OK)