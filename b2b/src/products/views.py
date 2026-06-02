from django.conf import settings
from django.db.models import Prefetch
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from skus.models import SKU
from .models import Product, Category
from .permissions import IsSellerOrServiceKey
from .serializers import (
    ProductSerializer,
    CategorySerializer,
    ProductDetailSerializer,
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