import base64
import json
import os
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from cart.models import CartItem
from .models import Order, OrderItem
from .serializers import CheckoutSerializer, OrderSerializer


B2B_BASE_URL = os.getenv("B2B_URL", "http://127.0.0.1:8001")
B2C_SERVICE_KEY = os.getenv("B2C_SERVICE_KEY", "b2c_service_key")


def error(code, message, http_status, details=None):
    data = {
        "code": code,
        "message": message,
    }

    if details is not None:
        data["details"] = details

    return Response(data, status=http_status)


def get_user_id_from_request(request):
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
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        return data.get("user_id") or data.get("sub")
    except Exception:
        return None


def b2b_get_products(product_ids):
    params = {
        "ids": ",".join([str(x) for x in product_ids]),
        "limit": 100,
        "offset": 0,
    }

    url = f"{B2B_BASE_URL}/api/v1/public/products/?" + urlencode(params)

    req = urllib_request.Request(
        url,
        method="GET",
        headers={
            "X-Service-Key": B2C_SERVICE_KEY,
        },
    )

    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))

    with opener.open(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def b2b_reserve(order_id, items, idempotency_key):
    url = f"{B2B_BASE_URL}/api/v1/inventory/reserve"

    body = {
        "order_id": str(order_id),
        "idempotency_key": idempotency_key,
        "items": [
            {
                "sku_id": str(item["sku_id"]),
                "quantity": item["quantity"],
            }
            for item in items
        ],
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib_request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Service-Key": B2C_SERVICE_KEY,
        },
    )

    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))

    try:
        with opener.open(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {}

        return exc.code, body


def b2b_unreserve(order):
    url = f"{B2B_BASE_URL}/api/v1/inventory/unreserve"

    body = {
        "order_id": str(order.id),
        "items": [
            {
                "sku_id": str(item.sku_id),
                "quantity": item.quantity,
            }
            for item in order.items.all()
        ],
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib_request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Service-Key": B2C_SERVICE_KEY,
        },
    )

    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))

    try:
        with opener.open(req, timeout=5) as resp:
            try:
                return resp.status, json.loads(resp.read().decode("utf-8"))
            except Exception:
                return resp.status, {}
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {}

        return exc.code, body


def build_order_items_from_cart(cart_items, products_data):
    products = products_data.get("items", []) if isinstance(products_data, dict) else products_data
    products_by_id = {str(product.get("id")): product for product in products}

    order_items = []
    failed_items = []

    for cart_item in cart_items:
        product = products_by_id.get(str(cart_item.product_id))

        if not product:
            failed_items.append({
                "sku_id": str(cart_item.sku_id),
                "reason": "PRODUCT_NOT_FOUND",
            })
            continue

        sku = None
        for item_sku in product.get("skus", []):
            if str(item_sku.get("id")) == str(cart_item.sku_id):
                sku = item_sku
                break

        if not sku:
            failed_items.append({
                "sku_id": str(cart_item.sku_id),
                "reason": "SKU_NOT_FOUND",
            })
            continue

        available_quantity = int(
            sku.get("available_quantity", sku.get("active_quantity", 0)) or 0
        )

        if available_quantity < cart_item.quantity:
            failed_items.append({
                "sku_id": str(cart_item.sku_id),
                "reason": "INSUFFICIENT_STOCK",
                "available_quantity": available_quantity,
            })
            continue

        price = int(sku.get("price", 0) or 0)
        discount = int(sku.get("discount", 0) or 0)
        unit_price = max(price - discount, 0)

        order_items.append({
            "product_id": str(cart_item.product_id),
            "sku_id": str(cart_item.sku_id),
            "product_title": product.get("name") or product.get("title") or "",
            "sku_name": sku.get("name") or "",
            "quantity": cart_item.quantity,
            "unit_price": unit_price,
            "line_total": unit_price * cart_item.quantity,
        })

    return order_items, failed_items


class CheckoutView(APIView):
    def post(self, request):
        user_id = get_user_id_from_request(request)

        if not user_id:
            return error(
                "UNAUTHORIZED",
                "Нужна авторизация",
                status.HTTP_401_UNAUTHORIZED,
            )

        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return error(
                "INVALID_REQUEST",
                "Некорректные данные checkout",
                status.HTTP_400_BAD_REQUEST,
                details=serializer.errors,
            )

        idempotency_key = serializer.validated_data["idempotency_key"]

        existing_order = Order.objects.filter(
            user_id=user_id,
            idempotency_key=idempotency_key,
        ).prefetch_related("items").first()

        if existing_order:
            return Response(
                OrderSerializer(existing_order).data,
                status=status.HTTP_200_OK,
            )

        cart_items = list(CartItem.objects.filter(user_id=user_id))

        if not cart_items:
            return error(
                "EMPTY_CART",
                "Корзина пуста",
                status.HTTP_400_BAD_REQUEST,
            )

        product_ids = list({str(item.product_id) for item in cart_items})

        try:
            products_data = b2b_get_products(product_ids)
        except (URLError, OSError):
            return error(
                "B2B_UNAVAILABLE",
                "B2B сервис временно недоступен",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        order_items_data, failed_items = build_order_items_from_cart(
            cart_items,
            products_data,
        )

        if failed_items:
            return error(
                "RESERVE_FAILED",
                "Не удалось зарезервировать товары",
                status.HTTP_409_CONFLICT,
                details={
                    "failed_items": failed_items,
                },
            )

        total_amount = sum(item["line_total"] for item in order_items_data)

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                    status="PAID",
                    total_amount=total_amount,
                )

                reserve_status, reserve_body = b2b_reserve(
                    order.id,
                    order_items_data,
                    idempotency_key,
                )

                if reserve_status != 200:
                    raise RuntimeError(json.dumps(reserve_body, ensure_ascii=False))

                for item in order_items_data:
                    OrderItem.objects.create(
                        order=order,
                        product_id=item["product_id"],
                        sku_id=item["sku_id"],
                        product_title=item["product_title"],
                        sku_name=item["sku_name"],
                        quantity=item["quantity"],
                        unit_price=item["unit_price"],
                        line_total=item["line_total"],
                    )

        except IntegrityError:
            existing_order = Order.objects.filter(
                user_id=user_id,
                idempotency_key=idempotency_key,
            ).prefetch_related("items").first()

            if existing_order:
                return Response(
                    OrderSerializer(existing_order).data,
                    status=status.HTTP_200_OK,
                )

            return error(
                "IDEMPOTENCY_CONFLICT",
                "Конфликт идемпотентности",
                status.HTTP_409_CONFLICT,
            )

        except RuntimeError as exc:
            try:
                details = json.loads(str(exc))
            except Exception:
                details = {}

            return error(
                "RESERVE_FAILED",
                "Не удалось зарезервировать товары",
                status.HTTP_409_CONFLICT,
                details=details,
            )

        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class CancelOrderView(APIView):
    def post(self, request, order_id):
        user_id = get_user_id_from_request(request)

        if not user_id:
            return error(
                "UNAUTHORIZED",
                "Нужна авторизация",
                status.HTTP_401_UNAUTHORIZED,
            )

        order = Order.objects.prefetch_related("items").filter(
            id=order_id,
            user_id=user_id,
        ).first()

        if not order:
            return error(
                "ORDER_NOT_FOUND",
                "Заказ не найден",
                status.HTTP_404_NOT_FOUND,
            )

        if order.status not in ["CREATED", "PAID", "ASSEMBLING"]:
            return error(
                "CANCEL_NOT_ALLOWED",
                "Заказ нельзя отменить в текущем статусе",
                status.HTTP_409_CONFLICT,
                details={
                    "current_status": order.status,
                    "allowed_statuses": ["CREATED", "PAID"],
                },
            )

        reason = request.data.get("reason", "")

        try:
            unreserve_status, unreserve_body = b2b_unreserve(order)

            if unreserve_status != 200:
                order.status = "CANCEL_PENDING"
                order.cancel_reason = reason
                order.save()

                return error(
                    "UNRESERVE_FAILED",
                    "Отмена принята, но снятие резерва будет повторено позже",
                    status.HTTP_202_ACCEPTED,
                    details=unreserve_body,
                )

            order.status = "CANCELLED"
            order.cancel_reason = reason
            order.cancelled_at = timezone.now()
            order.save()

            return Response(
                OrderSerializer(order).data,
                status=status.HTTP_200_OK,
            )

        except (URLError, OSError):
            order.status = "CANCEL_PENDING"
            order.cancel_reason = reason
            order.save()

            return Response(
                OrderSerializer(order).data,
                status=status.HTTP_202_ACCEPTED,
            )