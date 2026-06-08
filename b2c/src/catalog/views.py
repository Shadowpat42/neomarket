"""
B2C product card proxy view.

Fetches product data from B2B public catalog and transforms it to B2C schema.
Uses urllib (stdlib) instead of requests to avoid an extra dependency.
"""

import json
import os
from urllib import request as urllib_request
from urllib.error import URLError
from urllib.parse import urlencode

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import ProductCardSerializer

_B2B_BASE_URL = os.getenv("B2B_URL", "http://127.0.0.1:8001")
_B2C_SERVICE_KEY = os.getenv("B2C_SERVICE_KEY", "b2c_service_key")


def _fetch_from_b2b(product_id: str) -> tuple[int, dict]:
    """
    Call B2B GET /api/v1/public/products/?ids={product_id}.
    Returns (http_status_code, parsed_json_body).
    Raises URLError / OSError on network failure.
    """
    params = urlencode({"ids": product_id})
    url = f"{_B2B_BASE_URL}/api/v1/public/products/?{params}"

    req = urllib_request.Request(
        url,
        method="GET",
        headers={"X-Service-Key": _B2C_SERVICE_KEY},
    )
    with urllib_request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _transform_product(raw: dict) -> dict:
    """
    Map B2B PublicProductSerializer payload → B2C CatalogProductCard shape.

    Key transformations:
    - title → name  (B2B uses title, B2C OpenAPI requires name)
    - active_quantity → available_quantity  (B2C OpenAPI field name)
    - drop cost_price / reserved_quantity  (seller-only fields, must not leak)
    - compute min_price  (min price across SKUs with available_quantity > 0)
    - compute has_stock  (true if any SKU has available_quantity > 0)
    """
    skus_raw = raw.get("skus") or []
    skus = []
    for sku in skus_raw:
        available_qty = int(sku.get("active_quantity") or 0)
        skus.append(
            {
                "id": sku.get("id"),
                "name": sku.get("name"),
                "price": sku.get("price"),
                "discount": sku.get("discount", 0),
                "image": sku.get("image"),
                "available_quantity": available_qty,
                "in_stock": available_qty > 0,
                "characteristics": sku.get("characteristics") or [],
            }
        )

    in_stock_skus = [s for s in skus if s["in_stock"]]
    min_price = (
        min(s["price"] for s in in_stock_skus if s["price"] is not None)
        if in_stock_skus
        else None
    )
    has_stock = bool(in_stock_skus)

    return {
        "id": raw.get("id"),
        "name": raw.get("title") or raw.get("name", ""),
        "slug": raw.get("slug", ""),
        "description": raw.get("description", ""),
        "status": raw.get("status", ""),
        "min_price": min_price,
        "has_stock": has_stock,
        "images": raw.get("images") or [],
        "characteristics": raw.get("characteristics") or [],
        "skus": skus,
    }


class ProductCardView(APIView):
    def get(self, request, product_id):
        try:
            http_status, data = _fetch_from_b2b(str(product_id))
        except URLError:
            return Response(
                {
                    "code": "B2B_UNAVAILABLE",
                    "message": "B2B сервис временно недоступен",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if http_status == 404:
            return Response(
                {"code": "PRODUCT_NOT_FOUND", "message": "Товар не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if http_status != 200:
            return Response(
                {
                    "code": "B2B_ERROR",
                    "message": f"Ошибка B2B: {http_status}",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        products = data.get("items", []) if isinstance(data, dict) else data

        if not products:
            return Response(
                {"code": "PRODUCT_NOT_FOUND", "message": "Товар не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        product = _transform_product(products[0])
        serializer = ProductCardSerializer(data=product)
        serializer.is_valid()
        return Response(
            serializer.validated_data if serializer.validated_data else product,
            status=status.HTTP_200_OK,
        )
