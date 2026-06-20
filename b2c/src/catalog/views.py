"""
B2C catalog proxy views.

US-CAT-01:
- GET /api/v1/catalog/products
- GET /api/v1/catalog/facets

US-CAT-02:
- GET /api/v1/catalog/products with search

US-CAT-03:
- GET /api/v1/catalog/products/{id}

US-CAT-04:
- GET /api/v1/catalog/products/{id}/similar
"""

import json
import os
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import ProductCardSerializer, SimilarProductSerializer

_B2B_CATEGORIES_URL = "/api/v1/public/categories"


_B2B_BASE_URL = os.getenv("B2B_URL", "http://127.0.0.1:8001")
_B2C_SERVICE_KEY = os.getenv("B2C_SERVICE_KEY", "b2c_service_key")

ALLOWED_SORTS = ["price_asc", "price_desc", "popularity", "new"]
MIN_SEARCH_LENGTH = 3


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
        min(sku["price"] - sku.get("discount", 0) for sku in in_stock_skus if sku["price"] is not None)
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


def _transform_similar_product(raw):
    """Transform B2B product to B2C similar product format."""
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
        })

    in_stock_skus = [sku for sku in skus if sku["in_stock"]]

    min_price = (
        min(sku["price"] - sku.get("discount", 0) for sku in in_stock_skus if sku["price"] is not None)
        if in_stock_skus
        else None
    )

    return {
        "id": raw.get("id"),
        "name": raw.get("title") or raw.get("name", ""),
        "slug": raw.get("slug", ""),
        "min_price": min_price,
        "has_stock": bool(in_stock_skus),
        "images": raw.get("images") or [],
        "skus": skus,
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

        search = request.query_params.get("q") or request.query_params.get("search")
        
        # Validate search length for US-CAT-02
        if search and len(search) < MIN_SEARCH_LENGTH:
            return Response(
                {
                    "code": "SEARCH_QUERY_TOO_SHORT",
                    "message": "Поисковый запрос должен содержать минимум 3 символа",
                    "details": {
                        "min_length": MIN_SEARCH_LENGTH,
                        "actual_length": len(search),
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        params = {
            "limit": limit,
            "offset": offset,
            "sort": sort,
            "category_id": request.query_params.get("category_id"),
            "search": search,
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


class SimilarProductsView(APIView):
    """US-CAT-04: Get similar products for a given product."""
    
    def get(self, request, product_id):
        # First, get the product to find its category
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

        product = products[0]
        category_id = product.get("category", {}).get("id")
        product_title = product.get("title") or product.get("name", "")

        # Try to get similar products from the same category
        params = {
            "limit": 8,
            "offset": 0,
            "category_id": category_id,
        }

        try:
            http_status, data = _b2b_get("/api/v1/public/products/", params=params)
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

        similar_products_raw = data.get("items", []) if isinstance(data, dict) else data
        
        # Filter out the current product and transform
        similar_products = []
        for p in similar_products_raw:
            if str(p.get("id")) != str(product_id):
                similar_products.append(_transform_similar_product(p))

        # If we don't have enough products, try to get from parent category
        # or just return what we have (could be empty)
        if len(similar_products) < 8:
            # Try to get more products from any category as fallback
            # (B2B should handle parent category logic if needed)
            pass

        return Response(similar_products[:8], status=status.HTTP_200_OK)


def _fetch_flat_categories() -> list[dict]:
    """Fetch flat category list from B2B. Returns [{id, name, parent_id}]."""
    _, data = _b2b_get(_B2B_CATEGORIES_URL)
    return data if isinstance(data, list) else []


def _enrich_categories(flat: list[dict]) -> list[dict]:
    """
    Add `level` (0 = root) and `path` (list of names from root to node inclusive)
    to every category in the flat list.

    Algorithm: memoised DFS — each node is resolved at most once.
    Raises ValueError('orphan_node') if any parent_id references a missing node.
    """
    by_id: dict[str, dict] = {c["id"]: c for c in flat}

    # Pre-validate: no dangling parent references
    for c in flat:
        pid = c.get("parent_id")
        if pid and pid not in by_id:
            raise ValueError("orphan_node")

    memo: dict[str, tuple[int, list[str]]] = {}

    def _resolve(cat_id: str) -> tuple[int, list[str]]:
        if cat_id in memo:
            return memo[cat_id]
        node = by_id[cat_id]
        pid = node.get("parent_id")
        if pid:
            parent_level, parent_path = _resolve(pid)
            result: tuple[int, list[str]] = (parent_level + 1, parent_path + [node["name"]])
        else:
            result = (0, [node["name"]])
        memo[cat_id] = result
        return result

    enriched = []
    for c in flat:
        level, path = _resolve(c["id"])
        enriched.append({**c, "level": level, "path": path})
    return enriched


def _build_tree(flat: list[dict]) -> list[dict]:
    """
    Build a nested tree from a flat list (already enriched with level/path).
    Copies all fields from each node and adds an empty `children` list.
    Raises ValueError('orphan_node') if any node's parent_id is not in the list.
    """
    by_id = {c["id"]: dict(c, children=[]) for c in flat}

    for c in flat:
        pid = c.get("parent_id")
        if pid and pid not in by_id:
            raise ValueError("orphan_node")

    roots = []
    for node in by_id.values():
        pid = node.get("parent_id")
        if pid:
            by_id[pid]["children"].append(node)
        else:
            roots.append(node)
    return roots


def _breadcrumb_path(category_id: str, flat: list[dict]) -> list[dict]:
    """
    Walk parent chain from leaf to root, return path from root to leaf.
    Raises ValueError('orphan_node') on broken hierarchy.
    """
    by_id = {c["id"]: c for c in flat}
    if category_id not in by_id:
        raise KeyError(category_id)

    path = []
    cur_id = category_id
    visited = set()
    while cur_id:
        if cur_id in visited:
            raise ValueError("orphan_node")
        visited.add(cur_id)
        node = by_id.get(cur_id)
        if node is None:
            raise ValueError("orphan_node")
        path.append(node)
        cur_id = node.get("parent_id")
    path.reverse()
    return path


class CategoryFlatListView(APIView):
    """
    GET /api/v1/catalog/categories
    Returns flat list of all categories with computed level and path.
    Schema: CategoryRef[] — [{id, name, parent_id, level, path}].
    """

    def get(self, request):
        try:
            flat = _fetch_flat_categories()
        except (URLError, OSError):
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "B2B сервис временно недоступен"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except HTTPError as exc:
            return Response(
                {"code": "B2B_ERROR", "message": f"Ошибка B2B: {exc.code}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            enriched = _enrich_categories(flat)
        except ValueError:
            return Response(
                {"error": "orphan_node", "message": "category hierarchy is broken"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(enriched, status=status.HTTP_200_OK)


class CategoryTreeView(APIView):
    """
    GET /api/v1/catalog/categories/tree
    Returns full nested category tree for the B2C navigation menu.
    Response is a plain CategoryRef[] array (no wrapper).
    """

    def get(self, request):
        try:
            flat = _fetch_flat_categories()
        except (URLError, OSError):
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "B2B сервис временно недоступен"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except HTTPError as exc:
            return Response(
                {"code": "B2B_ERROR", "message": f"Ошибка B2B: {exc.code}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            enriched = _enrich_categories(flat)
            tree = _build_tree(enriched)
        except ValueError:
            return Response(
                {"error": "orphan_node", "message": "category hierarchy is broken"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response(tree, status=status.HTTP_200_OK)


class CategoryDetailView(APIView):
    """
    GET /api/v1/categories/{category_id}
    Returns flat category details fetched from B2B.
    """

    def get(self, request, category_id):
        try:
            flat = _fetch_flat_categories()
        except (URLError, OSError):
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "B2B сервис временно недоступен"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except HTTPError as exc:
            return Response(
                {"code": "B2B_ERROR", "message": f"Ошибка B2B: {exc.code}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        by_id = {c["id"]: c for c in flat}
        cat = by_id.get(str(category_id))
        if cat is None:
            return Response(
                {"code": "NOT_FOUND", "message": "Category not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Resolve parent details if available
        parent = None
        pid = cat.get("parent_id")
        if pid and pid in by_id:
            parent = {k: v for k, v in by_id[pid].items() if k != "parent_id"}

        return Response(
            {**cat, "parent": parent},
            status=status.HTTP_200_OK,
        )


class BreadcrumbsView(APIView):
    """
    GET /api/v1/breadcrumbs?category_id=<uuid>
    GET /api/v1/breadcrumbs?product_id=<uuid>
    Exactly one param required; returns path from root to the given node.
    """

    def get(self, request):
        category_id = request.query_params.get("category_id")
        product_id = request.query_params.get("product_id")

        # Exactly one param
        if category_id and product_id:
            return Response(
                {
                    "error": "ambiguous_param",
                    "message": "only one of category_id or product_id must be provided",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not category_id and not product_id:
            return Response(
                {
                    "error": "missing_param",
                    "message": "category_id or product_id must be provided",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        resolved_via = "category_id" if category_id else "product_id"

        # If product_id given, resolve to category_id via B2B product endpoint
        if product_id:
            try:
                _, data = _b2b_get(
                    "/api/v1/public/products/",
                    params={"ids": product_id},
                )
                items = data.get("items", []) if isinstance(data, dict) else data
                if not items:
                    return Response(
                        {"code": "NOT_FOUND", "message": "Product not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                cat_info = (items[0].get("category") or {})
                category_id = cat_info.get("id")
                if not category_id:
                    return Response(
                        {"code": "NOT_FOUND", "message": "Product has no category"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            except (URLError, OSError):
                return Response(
                    {"code": "B2B_UNAVAILABLE", "message": "B2B сервис временно недоступен"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            except HTTPError as exc:
                return Response(
                    {"code": "B2B_ERROR", "message": f"Ошибка B2B: {exc.code}"},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        # Fetch flat category list and build path
        try:
            flat = _fetch_flat_categories()
        except (URLError, OSError):
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "B2B сервис временно недоступен"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except HTTPError as exc:
            return Response(
                {"code": "B2B_ERROR", "message": f"Ошибка B2B: {exc.code}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            path = _breadcrumb_path(str(category_id), flat)
        except KeyError:
            return Response(
                {"code": "NOT_FOUND", "message": "Category not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError:
            return Response(
                {"error": "orphan_node", "message": "category hierarchy is broken"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        breadcrumbs = [
            {
                "id": node["id"],
                "name": node["name"],
                "level": idx,
                "is_current": idx == len(path) - 1,
            }
            for idx, node in enumerate(path)
        ]

        return Response(
            {
                "data": breadcrumbs,
                "meta": {
                    "resolved_via": resolved_via,
                    "category_id": str(category_id),
                },
            },
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
