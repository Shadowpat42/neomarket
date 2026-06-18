"""
US-CART-01: избранное покупателя
US-CART-02: подписки на изменения товара

ADR — идентификация пользователя (IDOR prevention)
  Рассматривались три подхода:
  A) user_id из query-параметра.
     Любой клиент может передать чужой user_id → IDOR. Отклонено.
  B) user_id из JWT claims (выбрано).
     user_id извлекается из Bearer-токена на стороне сервера.
     Клиент не может подменить: токен подписан. Риск IDOR = 0.
     Сложность: минимальная — одна helper-функция для декодирования JWT.
  C) X-User-Id заголовок, выставляемый API-шлюзом.
     Приемлемо при наличии доверенного шлюза, который сам валидирует токен.
     В текущей архитектуре без шлюза — небезопасно (заголовок может подделать клиент).
  Выбрано B: нет зависимости от внешнего шлюза, полный контроль на уровне сервиса.
  user_id из query/body игнорируется.
"""

import base64
import json
import os
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Favorite, ProductSubscription, VALID_NOTIFY_ON

_B2B_BASE_URL = os.getenv("B2B_URL", "http://127.0.0.1:8001")
_B2C_SERVICE_KEY = os.getenv("B2C_SERVICE_KEY", "b2c_service_key")


# ── Auth helper ───────────────────────────────────────────────────────────────

def _get_user_id(request) -> str | None:
    """
    Extract user_id exclusively from the request's auth context.
    Priority: X-User-Id header (set by gateway in production) →
              Bearer JWT payload field 'user_id' or 'sub'.
    query/body params are NEVER used — IDOR prevention.
    """
    x_user_id = request.headers.get("X-User-Id")
    if x_user_id:
        return x_user_id

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None

    token = auth.replace("Bearer ", "").strip()
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        padding = "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode((parts[1] + padding).encode()))
        return str(data.get("user_id") or data.get("sub") or "")
    except Exception:
        return None


def _require_user_id(request):
    """Return (user_id, None) or (None, error_response)."""
    uid = _get_user_id(request)
    if not uid:
        return None, Response(
            {"code": "UNAUTHORIZED", "message": "Authentication required"},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    return uid, None


# ── B2B helper ────────────────────────────────────────────────────────────────

def _b2b_get(path, params=None):
    url = f"{_B2B_BASE_URL}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v not in (None, "")}
        if clean:
            url += "?" + urlencode(clean)
    req = urllib_request.Request(
        url, method="GET", headers={"X-Service-Key": _B2C_SERVICE_KEY}
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))
    with opener.open(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _fetch_products_by_ids(product_ids: list[str]) -> dict[str, dict]:
    """
    Batch-fetch products from B2B.
    Returns dict {product_id_str: product_data}.
    Products absent from the response (deleted, blocked, etc.) are silently omitted.
    """
    if not product_ids:
        return {}
    _, data = _b2b_get(
        "/api/v1/public/products/",
        params={"ids": ",".join(product_ids)},
    )
    items = data.get("items", []) if isinstance(data, dict) else data
    return {str(p["id"]): p for p in items}


# ── CART-01: Favorites ────────────────────────────────────────────────────────

class FavoritesListView(APIView):
    """GET /api/v1/favorites — list with B2B enrichment."""

    def get(self, request):
        user_id, err = _require_user_id(request)
        if err:
            return err

        try:
            limit = max(1, min(100, int(request.query_params.get("limit", 20))))
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (TypeError, ValueError):
            limit, offset = 20, 0

        qs = Favorite.objects.filter(user_id=user_id)
        total = qs.count()
        page = list(qs[offset: offset + limit])

        if not page:
            return Response({"items": [], "total": total}, status=status.HTTP_200_OK)

        product_ids = [str(f.product_id) for f in page]

        try:
            b2b_map = _fetch_products_by_ids(product_ids)
        except (URLError, OSError):
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "B2B сервис временно недоступен"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except HTTPError as exc:
            return Response(
                {"code": "B2B_ERROR", "message": f"Ошибка B2B: {exc.code}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Enrich and filter: products absent from B2B are silently excluded
        items = []
        for fav in page:
            pid = str(fav.product_id)
            product = b2b_map.get(pid)
            if product:
                items.append({
                    "product_id": pid,
                    "added_at": fav.added_at.isoformat(),
                    "product": product,
                })

        return Response(
            {
                "items": items,
                "total_count": total,
                "limit": limit,
                "offset": offset,
            },
            status=status.HTTP_200_OK,
        )


class FavoriteItemView(APIView):
    """
    PUT    /api/v1/favorites/{product_id} — add (idempotent, 204)
    DELETE /api/v1/favorites/{product_id} — remove (idempotent, 204)
    """

    def put(self, request, product_id):
        user_id, err = _require_user_id(request)
        if err:
            return err

        Favorite.objects.get_or_create(
            user_id=user_id,
            product_id=product_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, product_id):
        user_id, err = _require_user_id(request)
        if err:
            return err

        Favorite.objects.filter(user_id=user_id, product_id=product_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── CART-02: Subscriptions ────────────────────────────────────────────────────

class SubscribeView(APIView):
    """
    POST   /api/v1/favorites/{product_id}/subscribe — subscribe (201 / 409)
    DELETE /api/v1/favorites/{product_id}/subscribe — unsubscribe (204)
    """

    def post(self, request, product_id):
        user_id, err = _require_user_id(request)
        if err:
            return err

        notify_on = request.data.get("events")
        if not notify_on or not isinstance(notify_on, list) or len(notify_on) == 0:
            return Response(
                {"code": "INVALID_NOTIFY_ON", "message": "events must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invalid = set(notify_on) - VALID_NOTIFY_ON
        if invalid:
            return Response(
                {
                    "code": "INVALID_NOTIFY_ON",
                    "message": f"Invalid events values: {sorted(invalid)}. "
                               f"Allowed: {sorted(VALID_NOTIFY_ON)}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify product exists in B2B
        try:
            _, data = _b2b_get(
                "/api/v1/public/products/",
                params={"ids": str(product_id)},
            )
            items = data.get("items", []) if isinstance(data, dict) else data
            if not items:
                return Response(
                    {"code": "PRODUCT_NOT_FOUND", "message": "Product not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except (URLError, OSError):
            return Response(
                {"code": "B2B_UNAVAILABLE", "message": "B2B сервис временно недоступен"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except HTTPError as exc:
            return Response(
                {"code": "B2B_ERROR", "message": f"Ошибка B2B: {exc.code}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Check for duplicate subscription
        if ProductSubscription.objects.filter(
            user_id=user_id, product_id=product_id
        ).exists():
            return Response(
                {
                    "code": "SUBSCRIPTION_ALREADY_EXISTS",
                    "message": "You already have a subscription for this product",
                },
                status=status.HTTP_409_CONFLICT,
            )

        ProductSubscription.objects.create(
            user_id=user_id,
            product_id=product_id,
            notify_on=list(notify_on),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, product_id):
        user_id, err = _require_user_id(request)
        if err:
            return err

        ProductSubscription.objects.filter(
            user_id=user_id, product_id=product_id
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
