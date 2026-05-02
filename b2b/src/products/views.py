from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from .models import Product, Category
from .serializers import ProductSerializer, CategorySerializer


class ProductListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data.copy()

        serializer = ProductSerializer(data=data)

        if serializer.is_valid():
            serializer.validated_data['seller_id'] = request.user.id
            product = serializer.save()
            return Response(
                ProductSerializer(product).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            {
                "code": "INVALID_PRODUCT_DATA",
                "message": "Некорректные данные товара",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST
        )


class ProductDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, product_id):
        try:
            return Product.objects.prefetch_related(
                "images",
                "characteristics"
            ).get(id=product_id)
        except Product.DoesNotExist:
            return None

    def _check_owner(self, product, user_id):
        if product.seller_id != user_id:
            raise PermissionDenied("У вас нет прав на изменение этого товара")
        
    def get(self, request, product_id):
        product = self.get_object(product_id)

        if product is None:
            return Response(
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ProductSerializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, product_id):
        product = self.get_object(product_id)

        if product is None:
            return Response(
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND
            )
        self._check_owner(product, request.user.id)
        
        serializer = ProductSerializer(product, data=request.data, partial=True)

        if serializer.is_valid():
            product = serializer.save()
            return Response(
                ProductSerializer(product).data,
                status=status.HTTP_200_OK
            )

        return Response(
            {
                "code": "INVALID_PRODUCT_DATA",
                "message": "Некорректные данные товара",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def delete(self, request, product_id):
        product = self.get_object(product_id)

        if product is None:
            return Response(
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND
            )
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

        if serializer.is_valid():
            category = serializer.save()
            return Response(
                CategorySerializer(category).data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            {
                "code": "INVALID_CATEGORY_DATA",
                "message": "Некорректные данные категории",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST
        )


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