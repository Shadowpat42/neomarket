"""
US-CART-04: баннеры на главной
US-CART-05: подборки товаров на главной
"""
import json
import os
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Banner, BannerEvent, Collection, CollectionProduct

_B2B_BASE_URL = os.getenv("B2B_URL", "http://127.0.0.1:8001")
_B2C_SERVICE_KEY = os.getenv("B2C_SERVICE_KEY", "b2c_service_key")


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


# ── US-CART-04: Banners ───────────────────────────────────────────────────────

class BannerListView(APIView):
    """
    GET /api/v1/home/banners
    Public endpoint. Returns active banners filtered by schedule, sorted by priority.
    """

    def get(self, request):
        from django.db.models import Q
        now = timezone.now()
        schedule_ok = (
            Q(start_at__isnull=True) | Q(start_at__lte=now)
        ) & (
            Q(end_at__isnull=True) | Q(end_at__gte=now)
        )
        qs = Banner.objects.filter(is_active=True).filter(schedule_ok).order_by("priority")

        items = [
            {
                "id": str(b.id),
                "title": b.title,
                "image_url": b.image_url,
                "link": b.link,
                "ordering": b.priority,
            }
            for b in qs
        ]
        return Response(items, status=status.HTTP_200_OK)


class BannerEventView(APIView):
    """
    POST /api/v1/banner-events
    CTR analytics: batch impression/click events.
    No auth required; user_id is optional (from JWT or omitted for anonymous).
    """

    def post(self, request):
        events = request.data.get("events")
        if not events or not isinstance(events, list):
            return Response(
                {"code": "EMPTY_EVENTS", "message": "events must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate banner IDs exist
        banner_ids = {str(e.get("banner_id")) for e in events if e.get("banner_id")}
        existing = set(
            str(bid) for bid in Banner.objects.filter(id__in=banner_ids).values_list("id", flat=True)
        )
        missing = banner_ids - existing
        if missing:
            return Response(
                {
                    "code": "BANNER_NOT_FOUND",
                    "message": f"Banners not found: {sorted(missing)}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve optional user_id (best-effort)
        user_id = _extract_user_id(request)
        occurred_at = timezone.now()

        to_create = []
        for ev in events:
            bid = ev.get("banner_id")
            etype = ev.get("event_type") or ev.get("event", "impression")
            if not bid:
                continue
            to_create.append(
                BannerEvent(
                    banner_id=bid,
                    user_id=user_id,
                    event=etype,
                    occurred_at=occurred_at,
                )
            )
        BannerEvent.objects.bulk_create(to_create)

        return Response({"ok": True, "count": len(to_create)}, status=status.HTTP_200_OK)


def _extract_user_id(request):
    """Best-effort: extract user_id from X-User-Id or JWT; None for anonymous."""
    uid = request.headers.get("X-User-Id")
    if uid:
        return uid
    import base64, json as json_lib
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    parts = auth.replace("Bearer ", "").split(".")
    if len(parts) < 2:
        return None
    try:
        padding = "=" * (-len(parts[1]) % 4)
        data = json_lib.loads(base64.urlsafe_b64decode(parts[1] + padding))
        return str(data.get("user_id") or data.get("sub") or "")
    except Exception:
        return None


# ── US-CART-05: Collections ───────────────────────────────────────────────────

class CollectionsListView(APIView):
    """
    GET /api/v1/catalog/collections
    Public. Returns active collections with products enriched from B2B, sorted by priority.
    Response is a plain Collection[] array (no pagination wrapper).
    """

    def get(self, request):
        from django.db.models import Q
        from datetime import date
        from collections import defaultdict

        today = date.today()
        qs = list(
            Collection.objects.filter(is_active=True).filter(
                Q(start_date__isnull=True) | Q(start_date__lte=today)
            ).order_by("priority")
        )

        if not qs:
            return Response([], status=status.HTTP_200_OK)

        # One DB query for all collection-product mappings
        col_ids = [c.id for c in qs]
        all_cps = CollectionProduct.objects.filter(
            collection_id__in=col_ids
        ).order_by("ordering")

        col_products_map: dict = defaultdict(list)
        for cp in all_cps:
            col_products_map[cp.collection_id].append(str(cp.product_id))

        all_product_ids = list({pid for pids in col_products_map.values() for pid in pids})

        # Single B2B batch call
        b2b_map: dict = {}
        if all_product_ids:
            try:
                _, data = _b2b_get(
                    "/api/v1/public/products/",
                    params={"ids": ",".join(all_product_ids)},
                )
                b2b_items = data.get("items", []) if isinstance(data, dict) else []
                b2b_map = {str(p["id"]): p for p in b2b_items}
            except Exception:
                pass

        items = []
        for col in qs:
            ordered_pids = col_products_map.get(col.id, [])
            products = [b2b_map[pid] for pid in ordered_pids if pid in b2b_map]
            items.append({
                "id": str(col.id),
                "name": col.title,
                "description": col.description,
                "cover_image_url": col.cover_image_url,
                "target_url": col.target_url,
                "products": products,
            })

        return Response(items, status=status.HTTP_200_OK)


class CollectionProductsView(APIView):
    """
    GET /api/v1/collections/{collection_id}/products
    Batch-enriches product list from B2B.
    Products absent from B2B (deleted/blocked) → unavailable_ids.
    """

    def get(self, request, collection_id):
        try:
            collection = Collection.objects.get(id=collection_id)
        except Collection.DoesNotExist:
            return Response(
                {"code": "NOT_FOUND", "message": "Collection not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            limit = max(1, min(100, int(request.query_params.get("limit", 20))))
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (TypeError, ValueError):
            limit, offset = 20, 0

        cp_qs = CollectionProduct.objects.filter(collection=collection).order_by("ordering")
        all_product_ids = [str(cp.product_id) for cp in cp_qs]
        page_ids = all_product_ids[offset: offset + limit]

        if not page_ids:
            return Response(
                {
                    "collection_id": str(collection.id),
                    "title": collection.title,
                    "items": [],
                    "unavailable_ids": [],
                    "total_products": len(all_product_ids),
                },
                status=status.HTTP_200_OK,
            )

        # Batch-fetch from B2B
        try:
            _, data = _b2b_get(
                "/api/v1/public/products/",
                params={"ids": ",".join(page_ids)},
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

        b2b_items = data.get("items", []) if isinstance(data, dict) else data
        found_ids = {str(p["id"]) for p in b2b_items}
        unavailable_ids = [pid for pid in page_ids if pid not in found_ids]

        return Response(
            {
                "collection_id": str(collection.id),
                "title": collection.title,
                "items": b2b_items,
                "unavailable_ids": unavailable_ids,
                "total_products": len(all_product_ids),
            },
            status=status.HTTP_200_OK,
        )
