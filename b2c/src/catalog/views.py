"""
B2C catalog proxy views.

US-CAT-01:
- GET /api/v1/catalog/products
- GET /api/v1/catalog/facets

US-CAT-03:
- GET /api/v1/catalog/products/{id}
"""

import json
import os
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import ProductCardSerializer


_B2B_BASE_URL = os.getenv("B2B_URL", "http://127.0.0.1:8001")
_B2C_SERVICE_KEY = os.getenv("B2C_SERVICE_KEY", "b2c_service_key")

ALLOWED_SORTS = ["price_asc", "price_desc", "popularity", "new"]


def _b2b_get(path, params=None):
    url = f"{_B2B_BASE_URL}{path}"

    if params:
        clean_params = {}
        for key, value in params.items():
            if value not in [None, ""]:
                clean_params[key] = value

        if clean_params:
            url += "?" + urlencode(clean_params)

    req = urllib_request.Request(
        url,
        method="GET",
        headers={"X-Service-Key": _B2C_SERVICE_KEY},
    )

    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))

    with opener.open(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _transform_product(raw):
    skus_raw = raw.get("skus") or []

    skus = []
    for sku in skus_raw:
        available_qty = int(sku.get("available_quantity", sku.get("active_quantity", 0)) or 0)

        skus.append({
            "id": sku.get("id"),
            "name": sku.get("name"),
            "price": sku.get("price"),
            "discount": sku.get("discount", 0),
            "image": sku.get("image"),
            "available_quantity": available_qty,
            "in_stock": available_qty > 0,
            "characteristics": sku.get("characteristics") or [],
        })

    in_stock_skus = [sku for sku in skus if sku["in_stock"]]

    min_price = (
        min(sku["price"] for sku in in_stock_skus if sku["price"] is not None)
        if in_stock_skus
        else None
    )

    return {
        "id": raw.get("id"),
        "name": raw.get("title") or raw.get("name", ""),
        "category": raw.get("category") or {},
        "slug": raw.get("slug", ""),
        "description": raw.get("description", ""),
        "status": raw.get("status", ""),
        "min_price": min_price,
        "has_stock": bool(in_stock_skus),
        "images": raw.get("images") or [],
        "characteristics": raw.get("characteristics") or [],
        "skus": skus,
    }


def _product_short(product):
    return {
        "id": product.get("id"),
        "name": product.get("name"),
        "slug": product.get("slug"),
        "description": product.get("description"),
        "min_price": product.get("min_price"),
        "has_stock": product.get("has_stock"),
        "images": product.get("images", []),
        "characteristics": product.get("characteristics", []),
        "skus": product.get("skus", []),
    }


class ProductListView(APIView):
    def get(self, request):
        sort = request.query_params.get("sort", "new")

        if sort not in ALLOWED_SORTS:
            return Response(
                {
                    "code": "INVALID_SORT",
                    "message": "Некорректная сортировка",
                    "details": {
                        "allowed": ALLOWED_SORTS,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        limit = request.query_params.get("limit", 20)
        offset = request.query_params.get("offset", 0)

        params = {
            "limit": limit,
            "offset": offset,
            "sort": sort,
            "category_id": request.query_params.get("category_id"),
            "search": request.query_params.get("q") or request.query_params.get("search"),
            "min_price": request.query_params.get("min_price"),
            "max_price": request.query_params.get("max_price"),
        }

        try:
            http_status, data = _b2b_get("/api/v1/public/products/", params=params)
        except (URLError, OSError):
            return Response(
                {
                    "code": "B2B_UNAVAILABLE",
                    "message": "B2B сервис временно недоступен",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except HTTPError as exc:
            return Response(
                {
                    "code": "B2B_ERROR",
                    "message": f"Ошибка B2B: {exc.code}",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if http_status != 200:
            return Response(
                {
                    "code": "B2B_ERROR",
                    "message": f"Ошибка B2B: {http_status}",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        products_raw = data.get("items", []) if isinstance(data, dict) else data
        products = [_product_short(_transform_product(product)) for product in products_raw]

        return Response(
            {
                "items": products,
                "total_count": data.get("total_count", len(products)) if isinstance(data, dict) else len(products),
                "limit": int(limit),
                "offset": int(offset),
            },
            status=status.HTTP_200_OK,
        )


class ProductCardView(APIView):
    def get(self, request, product_id):
        try:
            http_status, data = _b2b_get(
                "/api/v1/public/products/",
                params={"ids": str(product_id)},
            )
        except (URLError, OSError):
            return Response(
                {
                    "code": "B2B_UNAVAILABLE",
                    "message": "B2B сервис временно недоступен",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except HTTPError as exc:
            return Response(
                {
                    "code": "B2B_ERROR",
                    "message": f"Ошибка B2B: {exc.code}",
                },
                status=status.HTTP_502_BAD_GATEWAY,
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
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        product = _transform_product(products[0])
        serializer = ProductCardSerializer(data=product)
        serializer.is_valid()

        return Response(
            serializer.validated_data if serializer.validated_data else product,
            status=status.HTTP_200_OK,
        )


class FacetsView(APIView):
    def get(self, request):
        try:
            http_status, data = _b2b_get(
                "/api/v1/public/products/",
                params={
                    "limit": 100,
                    "offset": 0,
                    "category_id": request.query_params.get("category_id"),
                    "search": request.query_params.get("q") or request.query_params.get("search"),
                    "min_price": request.query_params.get("min_price"),
                    "max_price": request.query_params.get("max_price"),
                },
            )
        except (URLError, OSError):
            return Response(
                {
                    "code": "B2B_UNAVAILABLE",
                    "message": "B2B сервис временно недоступен",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except HTTPError as exc:
            return Response(
                {
                    "code": "B2B_ERROR",
                    "message": f"Ошибка B2B: {exc.code}",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if http_status != 200:
            return Response(
                {
                    "code": "B2B_ERROR",
                    "message": f"Ошибка B2B: {http_status}",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        products_raw = data.get("items", []) if isinstance(data, dict) else data
        products = [_transform_product(product) for product in products_raw]

        categories = {}
        characteristics = {}
        prices = []

        for product in products:
            category = product.get("category") or {}
            category_id = category.get("id")

            if category_id:
                if category_id not in categories:
                    categories[category_id] = {
                        "id": category_id,
                        "name": category.get("name", ""),
                        "count": 0,
                    }
                categories[category_id]["count"] += 1

            if product.get("min_price") is not None:
                prices.append(product["min_price"])

            for ch in product.get("characteristics", []):
                name = ch.get("name")
                value = ch.get("value")

                if not name or not value:
                    continue

                if name not in characteristics:
                    characteristics[name] = {}

                if value not in characteristics[name]:
                    characteristics[name][value] = 0

                characteristics[name][value] += 1

        characteristic_facets = []
        for name, values in characteristics.items():
            characteristic_facets.append({
                "name": name,
                "values": [
                    {
                        "value": value,
                        "count": count,
                    }
                    for value, count in values.items()
                ],
            })

        return Response(
            {
                "categories": list(categories.values()),
                "price": {
                    "min": min(prices) if prices else None,
                    "max": max(prices) if prices else None,
                },
                "characteristics": characteristic_facets,
            },
            status=status.HTTP_200_OK,
        )