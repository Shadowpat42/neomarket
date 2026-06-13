from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
import uuid

from products.models import Product
from products.permissions import IsB2CServiceKey
from .models import SKU, SKUImage
from .serializers import (
    SKUSerializer,
    SKUUpdateSerializer,
    SKUPutSerializer,
    SKUImageSerializer,
    SKUImageUpdateSerializer,
)
from shared_models.models import BaseProductStatus
from moderation_client import send_product_moderation_event
from .inventory import InsufficientStockError, reserve_skus, unreserve_skus


class SKUCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        product_id = request.data.get("product_id")
        had_skus_before = SKU.objects.filter(product_id=product_id).exists()

        serializer = SKUSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        sku = serializer.save()

        product = sku.product
        old_status = product.status

        # Canonic flow: first SKU for CREATED transitions -> ON_MODERATION + CREATED event.
        if not had_skus_before and old_status == BaseProductStatus.CREATED:
            product.status = BaseProductStatus.ON_MODERATION
            product.save(update_fields=["status"])

            try:
                send_product_moderation_event(
                    event_type="PRODUCT_CREATED",
                    product_id=product.id,
                    seller_id=product.seller_id,
                    idempotency_key=uuid.uuid4(),
                    occurred_at=timezone.now(),
                )
            except Exception:
                # Best-effort delivery: sellers shouldn't be blocked by moderation downtime.
                pass

        # Canonic flow: when adding another SKU to MODERATED/BLOCKED -> re-moderation.
        elif had_skus_before and old_status in {BaseProductStatus.MODERATED, BaseProductStatus.BLOCKED}:
            product.status = BaseProductStatus.ON_MODERATION
            product.save(update_fields=["status"])

            try:
                send_product_moderation_event(
                    event_type="PRODUCT_EDITED",
                    product_id=product.id,
                    seller_id=product.seller_id,
                    idempotency_key=uuid.uuid4(),
                    occurred_at=timezone.now(),
                )
            except Exception:
                pass

        return Response(SKUSerializer(sku).data, status=status.HTTP_201_CREATED)


class SKUDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, sku_id):
        try:
            return SKU.objects.select_related("product").prefetch_related(
                "images",
                "characteristics",
            ).get(id=sku_id)
        except SKU.DoesNotExist:
            return None

    def get(self, request, sku_id):
        sku = self.get_object(sku_id)

        if sku is None:
            return Response(
                {
                    "code": "SKU_NOT_FOUND",
                    "message": "SKU не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(SKUSerializer(sku).data, status=status.HTTP_200_OK)

    def _sku_not_found(self):
        return Response(
            {"code": "NOT_FOUND", "message": "SKU not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    def put(self, request, sku_id):
        sku = self.get_object(sku_id)
        if sku is None:
            return self._sku_not_found()

        product = sku.product

        if str(product.seller_id) != str(request.user.id):
            return Response(
                {
                    "code": "NOT_OWNER",
                    "message": "Product does not belong to the authenticated seller",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if product.status == BaseProductStatus.HARD_BLOCKED:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "Cannot edit hard-blocked product",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SKUPutSerializer(sku, data=request.data)
        serializer.is_valid(raise_exception=True)
        sku = serializer.save()

        # MODERATED or BLOCKED → re-queue for moderation
        if product.status in {BaseProductStatus.MODERATED, BaseProductStatus.BLOCKED}:
            product.status = BaseProductStatus.ON_MODERATION
            product.save(update_fields=["status"])
            try:
                send_product_moderation_event(
                    event_type="PRODUCT_EDITED",
                    product_id=product.id,
                    seller_id=product.seller_id,
                    idempotency_key=uuid.uuid4(),
                    occurred_at=timezone.now(),
                )
            except Exception:
                pass

        return Response(SKUSerializer(sku).data, status=status.HTTP_200_OK)

    def patch(self, request, sku_id):
        sku = self.get_object(sku_id)

        if sku is None:
            return Response(
                {
                    "code": "SKU_NOT_FOUND",
                    "message": "SKU не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SKUUpdateSerializer(sku, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        sku = serializer.save()
        return Response(SKUSerializer(sku).data, status=status.HTTP_200_OK)

    def delete(self, request, sku_id):
        sku = self.get_object(sku_id)

        if sku is None:
            return Response(
                {
                    "code": "SKU_NOT_FOUND",
                    "message": "SKU не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        sku.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SKUByProductView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        try:
            Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        skus = SKU.objects.filter(product_id=product_id).prefetch_related(
            "images",
            "characteristics",
        )

        return Response(SKUSerializer(skus, many=True).data, status=status.HTTP_200_OK)


class SKUImageCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, sku_id):
        try:
            sku = SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return Response(
                {
                    "code": "SKU_NOT_FOUND",
                    "message": "SKU не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SKUImageSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)
        image = serializer.save(sku=sku)
        return Response(SKUImageSerializer(image).data, status=status.HTTP_201_CREATED)


class SKUImageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, image_id):
        try:
            return SKUImage.objects.get(id=image_id)
        except SKUImage.DoesNotExist:
            return None

    def patch(self, request, image_id):
        image = self.get_object(image_id)

        if image is None:
            return Response(
                {
                    "code": "SKU_IMAGE_NOT_FOUND",
                    "message": "Изображение SKU не найдено",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SKUImageUpdateSerializer(image, data=request.data, partial=True)

        serializer.is_valid(raise_exception=True)
        image = serializer.save()
        return Response(SKUImageSerializer(image).data, status=status.HTTP_200_OK)

    def delete(self, request, image_id):
        image = self.get_object(image_id)

        if image is None:
            return Response(
                {
                    "code": "SKU_IMAGE_NOT_FOUND",
                    "message": "Изображение SKU не найдено",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReserveView(APIView):
    """
    POST /api/v1/inventory/reserve
    All-or-nothing SKU reservation (called by B2C at checkout).
    Requires X-Service-Key == B2C_SERVICE_KEY.
    Idempotent by idempotency_key.
    """

    permission_classes = [IsB2CServiceKey]

    def post(self, request):
        idempotency_key = request.data.get("idempotency_key")
        order_id = request.data.get("order_id")
        items = request.data.get("items")

        if not idempotency_key:
            return Response(
                {"code": "INVALID_REQUEST", "message": "idempotency_key is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not order_id:
            return Response(
                {"code": "INVALID_REQUEST", "message": "order_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not items:
            return Response(
                {"code": "INVALID_REQUEST", "message": "items is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result, _ = reserve_skus(
                idempotency_key=idempotency_key,
                order_id=order_id,
                items=items,
            )
        except InsufficientStockError as exc:
            return Response(
                {
                    "code": "INSUFFICIENT_STOCK",
                    "message": "Недостаточно остатка для одного или нескольких SKU",
                    "details": {"failed_items": exc.failed_items},
                },
                status=status.HTTP_409_CONFLICT,
            )
        except ValueError as exc:
            return Response(
                {"code": "NOT_FOUND", "message": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(result, status=status.HTTP_200_OK)


class UnreserveView(APIView):
    """
    POST /api/v1/inventory/unreserve
    Compensating transaction: release SKU reservation on order cancellation.
    Requires X-Service-Key == B2C_SERVICE_KEY.
    """

    permission_classes = [IsB2CServiceKey]

    def post(self, request):
        order_id = request.data.get("order_id")
        items = request.data.get("items")

        if not order_id:
            return Response(
                {"code": "INVALID_REQUEST", "message": "order_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not items:
            return Response(
                {"code": "INVALID_REQUEST", "message": "items is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = unreserve_skus(order_id=order_id, items=items)
        return Response(result, status=status.HTTP_200_OK)