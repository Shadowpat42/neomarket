from django.conf import settings
from django.db import transaction
from django.db.models import Exists, F, Min, OuterRef, Prefetch, Q, Subquery
from rest_framework import serializers as drf_serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from skus.models import SKU
from .models import (
    BlockingReason,
    ProcessedModerationEvent,
    Product,
    ProductFieldReport,
    Category,
)
from .permissions import IsSellerOrServiceKey, IsB2CServiceKey, IsModerationServiceKey
from .serializers import (
    ProductSerializer,
    CategorySerializer,
    ProductDetailSerializer,
    PublicProductSerializer,
)
from shared_models.models import BaseProductStatus
from b2c_client import notify_product_blocked
from moderation_client import send_product_moderation_event
import uuid
from django.utils import timezone


class ProductListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ProductSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save(seller_id=request.user.id)
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class ProductDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [IsSellerOrServiceKey()]
        return [IsAuthenticated()]

    def _detail_queryset(self):
        sku_qs = SKU.objects.prefetch_related("images", "characteristics")
        return Product.objects.select_related("category").prefetch_related(
            "images",
            "characteristics",
            "field_reports",
            Prefetch("skus", queryset=sku_qs),
        )

    def get_object(self, product_id):
        try:
            return self._detail_queryset().get(id=product_id)
        except Product.DoesNotExist:
            return None

    def _is_service_request(self, request) -> bool:
        service_key = request.headers.get("X-Service-Key")
        return bool(service_key and service_key == settings.B2B_SERVICE_KEY)

    def _check_owner(self, product, user_id):
        if product.seller_id != user_id:
            raise PermissionDenied("У вас нет прав на изменение этого товара")

    def _product_not_found_response(self):
        return Response(
            {"code": "NOT_FOUND", "message": "Product not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    def get(self, request, product_id):
        product = self.get_object(product_id)

        if product is None:
            return self._product_not_found_response()

        if not self._is_service_request(request):
            if str(product.seller_id) != str(request.user.id):
                return self._product_not_found_response()

        serializer = ProductDetailSerializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _hard_blocked_response(self):
        return Response(
            {
                "code": "FORBIDDEN",
                "message": "Cannot edit hard-blocked product",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    def _not_owner_response(self):
        return Response(
            {
                "code": "NOT_OWNER",
                "message": "Product does not belong to the authenticated seller",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    def put(self, request, product_id):
        product = self.get_object(product_id)
        if product is None:
            return self._product_not_found_response()

        if str(product.seller_id) != str(request.user.id):
            return self._not_owner_response()

        if product.status == BaseProductStatus.HARD_BLOCKED:
            return self._hard_blocked_response()

        old_status = product.status

        serializer = ProductSerializer(product, data=request.data)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()

        # MODERATED or BLOCKED → re-queue for moderation
        if old_status in {BaseProductStatus.MODERATED, BaseProductStatus.BLOCKED}:
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

        return Response(ProductDetailSerializer(self.get_object(product_id)).data,
                        status=status.HTTP_200_OK)

    def patch(self, request, product_id):
        product = self.get_object(product_id)

        if product is None:
            return self._product_not_found_response()
        self._check_owner(product, request.user.id)

        if product.status == BaseProductStatus.HARD_BLOCKED:
            return self._hard_blocked_response()

        serializer = ProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductSerializer(product).data, status=status.HTTP_200_OK)

    def delete(self, request, product_id):
        product = self.get_object(product_id)

        if product is None:
            return self._product_not_found_response()
        self._check_owner(product, request.user.id)

        if product.status == BaseProductStatus.HARD_BLOCKED:
            return self._hard_blocked_response()

        # B2B-4: Check if already deleted
        if product.deleted:
            return Response(
                {"code": "INVALID_REQUEST", "message": "Product already deleted"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # B2B-4: Soft delete
        product.deleted = True
        product.save(update_fields=["deleted"])

        # B2B-4: Send events (best-effort)
        sku_ids = [str(sku.id) for sku in product.skus.all()]

        try:
            send_product_moderation_event(
                event_type="PRODUCT_DELETED",
                product_id=product.id,
                seller_id=product.seller_id,
                idempotency_key=uuid.uuid4(),
                occurred_at=timezone.now(),
            )
        except Exception:
            pass

        try:
            from b2c_client import notify_product_deleted
            notify_product_deleted(
                product_id=product.id,
                sku_ids=sku_ids,
                idempotency_key=str(uuid.uuid4()),
            )
        except Exception:
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)
    
class ProductListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Product.objects.filter(seller_id=request.user.id)
        include_deleted = request.query_params.get("include_deleted", "false").lower()
        if include_deleted != "true":
            qs = qs.filter(deleted=False)
        serializer = ProductSerializer(qs, many=True)
        return Response(serializer.data)

class ProductCatalogView(APIView):
    """
    GET /api/v1/public/products/
    B2C service-to-service catalog. Requires X-Service-Key == B2C_SERVICE_KEY.
    Bearer JWT is intentionally rejected (see IsB2CServiceKey).
    """

    permission_classes = [IsB2CServiceKey]

    _SORT_MAP = {
        "price_asc": "min_sku_price",
        "price_desc": "-min_sku_price",
        "date_desc": "-created_at",
        "created_desc": "-created_at",
    }

    def _visible_queryset(self):
        """Products visible on vitrine: MODERATED, not deleted, ≥1 active SKU."""
        has_active_sku = SKU.objects.filter(
            product=OuterRef("pk"),
            stock_quantity__gt=F("reserved_quantity"),
        )
        sku_qs = SKU.objects.prefetch_related("images", "characteristics")
        return (
            Product.objects.select_related("category")
            .prefetch_related(
                "images",
                "characteristics",
                Prefetch("skus", queryset=sku_qs),
            )
            .filter(
                status="MODERATED",
                deleted=False,
            )
            .filter(Exists(has_active_sku))
        )

    def _apply_filters(self, qs, request):
        category_id = request.query_params.get("category_id")
        if category_id:
            qs = qs.filter(category_id=category_id)

        search = request.query_params.get("search", "").strip()
        if len(search) >= 3:
            qs = qs.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        ids_param = request.query_params.get("ids", "").strip()
        if ids_param:
            id_list = [i.strip() for i in ids_param.split(",") if i.strip()]
            qs = qs.filter(id__in=id_list)

        return qs

    def _apply_sort(self, qs, sort: str):
        order_field = self._SORT_MAP.get(sort, "-created_at")
        if "price" in order_field:
            min_price_sq = (
                SKU.objects.filter(product=OuterRef("pk"))
                .values("product")
                .annotate(mp=Min("price"))
                .values("mp")
            )
            qs = qs.annotate(min_sku_price=Subquery(min_price_sq))
        return qs.order_by(order_field)

    def get(self, request):
        try:
            limit = max(1, min(100, int(request.query_params.get("limit", 20))))
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (TypeError, ValueError):
            limit, offset = 20, 0

        sort = request.query_params.get("sort", "created_desc")

        qs = self._visible_queryset()
        qs = self._apply_filters(qs, request)
        qs = self._apply_sort(qs, sort)

        total_count = qs.count()
        page = qs[offset: offset + limit]

        items = PublicProductSerializer(page, many=True).data

        return Response(
            {
                "items": items,
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
            },
            status=status.HTTP_200_OK,
        )


class CategoryListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        categories = Category.objects.all().order_by("name")
        serializer = CategorySerializer(categories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = serializer.save()
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, category_id):
        try:
            return Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return None

    def get(self, request, category_id):
        category = self.get_object(category_id)

        if category is None:
            return Response(
                {
                    "code": "CATEGORY_NOT_FOUND",
                    "message": "Категория не найдена",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            CategorySerializer(category).data,
            status=status.HTTP_200_OK
        )


# ─── Input serializers (only used for validation, not stored) ────────────────


class _FieldReportInputSerializer(drf_serializers.Serializer):
    field_name = drf_serializers.CharField()
    sku_id = drf_serializers.UUIDField(required=False, allow_null=True)
    comment = drf_serializers.CharField()


class _BlockingReasonInputSerializer(drf_serializers.Serializer):
    id = drf_serializers.UUIDField()
    title = drf_serializers.CharField(required=False, default="")
    comment = drf_serializers.CharField(required=False, default="")


class _ModerationEventInputSerializer(drf_serializers.Serializer):
    idempotency_key = drf_serializers.UUIDField()
    product_id = drf_serializers.UUIDField()
    # Accept both OpenAPI name ("event_type") and canon-flow name ("status")
    event_type = drf_serializers.ChoiceField(
        choices=["MODERATED", "BLOCKED"], required=False
    )
    status = drf_serializers.ChoiceField(
        choices=["MODERATED", "BLOCKED"], required=False
    )
    hard_block = drf_serializers.BooleanField(required=False, default=False)
    # Full object (canon flow) or just ID (OpenAPI)
    blocking_reason = _BlockingReasonInputSerializer(required=False, allow_null=True)
    blocking_reason_id = drf_serializers.UUIDField(required=False, allow_null=True)
    moderator_comment = drf_serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    field_reports = _FieldReportInputSerializer(many=True, required=False, default=list)
    occurred_at = drf_serializers.DateTimeField(required=False)

    def validate(self, attrs):
        event_type = attrs.get("event_type") or attrs.get("status")
        if not event_type:
            raise drf_serializers.ValidationError(
                "event_type (or status) is required"
            )
        attrs["_event_type"] = event_type
        return attrs


class ModerationEventView(APIView):
    """
    POST /api/v1/moderation/events

    Receives moderation decisions from Moderation Service and applies them:
    - MODERATED  → status=MODERATED, clear blocking data
    - BLOCKED (soft) → status=BLOCKED, save field_reports, cascade to B2C
    - BLOCKED (hard) → status=HARD_BLOCKED, cascade to B2C

    Idempotent: second request with the same idempotency_key returns 204
    without any side effects.
    """

    permission_classes = [IsModerationServiceKey]

    def post(self, request):
        serializer = _ModerationEventInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        event_type = data["_event_type"]
        hard_block = data.get("hard_block", False)

        send_blocked_event = False
        product_id_for_b2c = None
        sku_ids_for_b2c: list[str] = []
        idempotency_key_for_b2c: str | None = None

        with transaction.atomic():
            # ── idempotency: insert-first approach inside the transaction ──
            _, is_new = ProcessedModerationEvent.objects.get_or_create(
                idempotency_key=data["idempotency_key"]
            )
            if not is_new:
                return Response(status=status.HTTP_204_NO_CONTENT)

            try:
                product = Product.objects.prefetch_related("skus").get(
                    id=data["product_id"]
                )
            except Product.DoesNotExist:
                return Response(
                    {"code": "NOT_FOUND", "message": "Product not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if event_type == "MODERATED":
                self._apply_moderated(product)
            else:
                self._apply_blocked(product, data, hard_block)
                send_blocked_event = True
                product_id_for_b2c = product.id
                sku_ids_for_b2c = [str(s.id) for s in product.skus.all()]
                idempotency_key_for_b2c = str(data["idempotency_key"])

        # ── best-effort B2C notification (outside transaction) ────────────
        if send_blocked_event:
            try:
                notify_product_blocked(
                    product_id=product_id_for_b2c,
                    sku_ids=sku_ids_for_b2c,
                    idempotency_key=idempotency_key_for_b2c,
                )
            except Exception:
                pass

        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_moderated(product: Product) -> None:
        """Set status=MODERATED and clear all blocking data."""
        product.status = BaseProductStatus.MODERATED
        product.blocking_reason_id = None
        product.moderator_comment = None
        product.save(update_fields=["status", "blocking_reason_id", "moderator_comment"])
        product.field_reports.all().delete()

    @staticmethod
    def _apply_blocked(product: Product, data: dict, hard_block: bool) -> None:
        """Set status=BLOCKED or HARD_BLOCKED and persist blocking data."""
        new_status = (
            BaseProductStatus.HARD_BLOCKED if hard_block else BaseProductStatus.BLOCKED
        )

        # Resolve blocking_reason_id: prefer the full object, fall back to UUID field
        blocking_reason_obj = data.get("blocking_reason")
        blocking_reason_id = None
        if blocking_reason_obj:
            br_id = blocking_reason_obj.get("id")
            br_title = blocking_reason_obj.get("title", "")
            if br_id:
                BlockingReason.objects.update_or_create(
                    id=br_id, defaults={"title": br_title}
                )
                blocking_reason_id = br_id
            # Use comment from inline object if top-level not provided
            if not data.get("moderator_comment") and blocking_reason_obj.get("comment"):
                data = dict(data, moderator_comment=blocking_reason_obj["comment"])
        elif data.get("blocking_reason_id"):
            blocking_reason_id = data["blocking_reason_id"]

        product.status = new_status
        product.blocking_reason_id = blocking_reason_id
        product.moderator_comment = data.get("moderator_comment")
        product.save(update_fields=["status", "blocking_reason_id", "moderator_comment"])

        # Replace field_reports (delete stale, insert fresh)
        product.field_reports.all().delete()
        field_reports = data.get("field_reports") or []
        if field_reports:
            ProductFieldReport.objects.bulk_create(
                [
                    ProductFieldReport(
                        product=product,
                        field_name=fr["field_name"],
                        sku_id=fr.get("sku_id"),
                        comment=fr["comment"],
                    )
                    for fr in field_reports
                ]
            )