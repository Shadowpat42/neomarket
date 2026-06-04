from django.conf import settings
from django.db.models import Exists, F, Min, OuterRef, Prefetch, Q, Subquery
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from skus.models import SKU
from .models import Product, Category
from .permissions import IsSellerOrServiceKey, IsB2CServiceKey
from .serializers import (
    ProductSerializer,
    CategorySerializer,
    ProductDetailSerializer,
    PublicProductSerializer,
)


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

    def patch(self, request, product_id):
        product = self.get_object(product_id)

        if product is None:
            return self._product_not_found_response()
        self._check_owner(product, request.user.id)
        
        serializer = ProductSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = serializer.save()
        return Response(ProductSerializer(product).data, status=status.HTTP_200_OK)
    
    def delete(self, request, product_id):
        product = self.get_object(product_id)

        if product is None:
            return self._product_not_found_response()
        self._check_owner(product, request.user.id)
        product.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
class ProductListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        products = Product.objects.filter(seller_id=request.user.id)
        serializer = ProductSerializer(products, many=True)
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