import base64
import json
import os
from urllib import request as urllib_request
from urllib.error import URLError
from urllib.parse import urlencode

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import CartItem
from .serializers import AddCartItemSerializer, UpdateCartItemSerializer


B2B_BASE_URL = os.getenv("B2B_URL", "http://127.0.0.1:8001")
B2C_SERVICE_KEY = os.getenv("B2C_SERVICE_KEY", "b2c_service_key")


def error(code, message, http_status):
    return Response({"code": code, "message": message}, status=http_status)


def get_user_id_from_request(request):
    """
    MVP:
    1. Если есть X-User-Id - используем его как user_id.
    2. Если есть Bearer JWT - пробуем достать user_id/sub из payload без проверки подписи.
    В production JWT должен валидироваться нормально.
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
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        return data.get("user_id") or data.get("sub")
    except Exception:
        return None


def get_cart_identity(request):
    user_id = get_user_id_from_request(request)

    if user_id:
        return {"user_id": user_id, "session_id": None, "is_auth": True}

    session_id = request.headers.get("X-Session-Id")
    if session_id:
        return {"user_id": None, "session_id": session_id, "is_auth": False}

    return None


def cart_queryset(identity):
    if identity["is_auth"]:
        return CartItem.objects.filter(user_id=identity["user_id"])
    return CartItem.objects.filter(session_id=identity["session_id"])


def fetch_b2b_products(product_ids=None):
    params = {}
    if product_ids:
        params["ids"] = ",".join([str(x) for x in product_ids])

    url = f"{B2B_BASE_URL}/api/v1/public/products/"
    if params:
        url += "?" + urlencode(params)

    req = urllib_request.Request(
        url,
        method="GET",
        headers={"X-Service-Key": B2C_SERVICE_KEY},
    )

    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))
    with opener.open(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_sku_in_b2b(sku_id):
    data = fetch_b2b_products()
    products = data.get("items", []) if isinstance(data, dict) else data

    for product in products:
        for sku in product.get("skus", []):
            if str(sku.get("id")) == str(sku_id):
                return product, sku

    return None, None


def build_cart_response(items):
    product_ids = list({str(item.product_id) for item in items})

    try:
        data = fetch_b2b_products(product_ids)
    except (URLError, OSError):
        raise

    products = data.get("items", []) if isinstance(data, dict) else data
    products_by_id = {str(p.get("id")): p for p in products}

    response_items = []
    total_amount = 0
    total_items = 0
    unavailable_count = 0
    checkout_items = []

    for item in items:
        product = products_by_id.get(str(item.product_id))

        if not product:
            response_items.append({
                "id": str(item.id),
                "product_id": str(item.product_id),
                "sku_id": str(item.sku_id),
                "quantity": item.quantity,
                "available": False,
                "unavailable_reason": "PRODUCT_DELETED",
                "line_total": 0,
            })
            unavailable_count += 1
            total_items += item.quantity
            continue

        sku = None
        for s in product.get("skus", []):
            if str(s.get("id")) == str(item.sku_id):
                sku = s
                break

        if not sku:
            response_items.append({
                "id": str(item.id),
                "product_id": str(item.product_id),
                "sku_id": str(item.sku_id),
                "quantity": item.quantity,
                "product": product,
                "available": False,
                "unavailable_reason": "PRODUCT_DELETED",
                "line_total": 0,
            })
            unavailable_count += 1
            total_items += item.quantity
            continue

        available_quantity = int(
            sku.get("available_quantity", sku.get("active_quantity", 0)) or 0
        )

        price = int(sku.get("price", 0) or 0)
        discount = int(sku.get("discount", 0) or 0)
        final_price = max(price - discount, 0)

        if available_quantity <= 0:
            available = False
            unavailable_reason = "OUT_OF_STOCK"
            line_total = 0
            unavailable_count += 1
        else:
            available = True
            unavailable_reason = None
            line_total = final_price * item.quantity
            total_amount += line_total
            checkout_items.append({
                "sku_id": str(item.sku_id),
                "quantity": item.quantity,
            })

        total_items += item.quantity

        response_items.append({
            "id": str(item.id),
            "product_id": str(item.product_id),
            "sku_id": str(item.sku_id),
            "quantity": item.quantity,
            "product": {
                "id": product.get("id"),
                "name": product.get("name") or product.get("title"),
                "slug": product.get("slug"),
                "images": product.get("images", []),
            },
            "sku": {
                "id": sku.get("id"),
                "name": sku.get("name"),
                "price": price,
                "discount": discount,
                "image": sku.get("image"),
                "available_quantity": available_quantity,
            },
            "available": available,
            "unavailable_reason": unavailable_reason,
            "line_total": line_total,
        })

    return {
        "items": response_items,
        "summary": {
            "total_amount": total_amount,
            "total_items": total_items,
            "unavailable_count": unavailable_count,
            "checkout_ready": len(response_items) > 0 and unavailable_count == 0,
        },
        "checkout_payload": {
            "items": checkout_items,
        },
    }


class CartView(APIView):
    def get(self, request):
        identity = get_cart_identity(request)
        if not identity:
            return error(
                "MISSING_CART_IDENTITY",
                "Нужен Authorization или X-Session-Id",
                status.HTTP_400_BAD_REQUEST,
            )

        items = list(cart_queryset(identity))

        try:
            data = build_cart_response(items)
        except (URLError, OSError):
            return error(
                "B2B_UNAVAILABLE",
                "B2B сервис временно недоступен",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(data, status=status.HTTP_200_OK)

    def delete(self, request):
        identity = get_cart_identity(request)
        if not identity:
            return error(
                "MISSING_CART_IDENTITY",
                "Нужен Authorization или X-Session-Id",
                status.HTTP_400_BAD_REQUEST,
            )

        cart_queryset(identity).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemCreateView(APIView):
    def post(self, request):
        identity = get_cart_identity(request)
        if not identity:
            return error(
                "MISSING_CART_IDENTITY",
                "Нужен Authorization или X-Session-Id",
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = AddCartItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "code": "INVALID_REQUEST",
                    "message": "Некорректные данные",
                    "details": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        sku_id = serializer.validated_data["sku_id"]
        quantity = serializer.validated_data["quantity"]

        try:
            product, sku = find_sku_in_b2b(sku_id)
        except (URLError, OSError):
            return error(
                "B2B_UNAVAILABLE",
                "B2B сервис временно недоступен",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not product or not sku:
            return error(
                "SKU_NOT_FOUND",
                "SKU не найден или недоступен",
                status.HTTP_404_NOT_FOUND,
            )

        available_quantity = int(
            sku.get("available_quantity", sku.get("active_quantity", 0)) or 0
        )

        if available_quantity < quantity:
            return Response(
                {
                    "code": "INSUFFICIENT_STOCK",
                    "message": "Недостаточно товара в наличии",
                    "details": {
                        "available_quantity": available_quantity,
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        filters = {"sku_id": sku_id}
        if identity["is_auth"]:
            filters["user_id"] = identity["user_id"]
            defaults = {
                "session_id": None,
                "product_id": product["id"],
                "quantity": quantity,
            }
        else:
            filters["session_id"] = identity["session_id"]
            defaults = {
                "user_id": None,
                "product_id": product["id"],
                "quantity": quantity,
            }

        item, created = CartItem.objects.get_or_create(
            **filters,
            defaults=defaults,
        )

        if not created:
            item.quantity += quantity
            item.product_id = product["id"]
            item.save()
            http_status = status.HTTP_200_OK
        else:
            http_status = status.HTTP_201_CREATED

        return Response(
            {
                "id": str(item.id),
                "product_id": str(item.product_id),
                "sku_id": str(item.sku_id),
                "quantity": item.quantity,
            },
            status=http_status,
        )


class CartItemDetailView(APIView):
    def patch(self, request, sku_id):
        identity = get_cart_identity(request)
        if not identity:
            return error(
                "MISSING_CART_IDENTITY",
                "Нужен Authorization или X-Session-Id",
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = UpdateCartItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "code": "INVALID_QUANTITY",
                    "message": "Количество должно быть больше 0",
                    "details": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = cart_queryset(identity).filter(sku_id=sku_id).first()
        if not item:
            return error("NOT_FOUND", "Позиция не найдена", status.HTTP_404_NOT_FOUND)

        item.quantity = serializer.validated_data["quantity"]
        item.save()

        return Response(
            {
                "id": str(item.id),
                "product_id": str(item.product_id),
                "sku_id": str(item.sku_id),
                "quantity": item.quantity,
            },
            status=status.HTTP_200_OK,
        )

    def delete(self, request, sku_id):
        identity = get_cart_identity(request)
        if not identity:
            return error(
                "MISSING_CART_IDENTITY",
                "Нужен Authorization или X-Session-Id",
                status.HTTP_400_BAD_REQUEST,
            )

        item = cart_queryset(identity).filter(sku_id=sku_id).first()
        if not item:
            return error("NOT_FOUND", "Позиция не найдена", status.HTTP_404_NOT_FOUND)

        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartMergeView(APIView):
    def post(self, request):
        user_id = get_user_id_from_request(request)
        session_id = request.headers.get("X-Session-Id")

        if not user_id:
            return error("UNAUTHORIZED", "Нужна авторизация", status.HTTP_401_UNAUTHORIZED)

        if not session_id:
            return error(
                "MISSING_CART_IDENTITY",
                "Нужен X-Session-Id гостевой корзины",
                status.HTTP_400_BAD_REQUEST,
            )

        guest_items = CartItem.objects.filter(session_id=session_id)

        for guest_item in guest_items:
            auth_item = CartItem.objects.filter(
                user_id=user_id,
                sku_id=guest_item.sku_id,
            ).first()

            if auth_item:
                auth_item.quantity = max(auth_item.quantity, guest_item.quantity)
                auth_item.save()
                guest_item.delete()
            else:
                guest_item.user_id = user_id
                guest_item.session_id = None
                guest_item.save()

        items = list(CartItem.objects.filter(user_id=user_id))

        try:
            data = build_cart_response(items)
        except (URLError, OSError):
            return error(
                "B2B_UNAVAILABLE",
                "B2B сервис временно недоступен",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(data, status=status.HTTP_200_OK)