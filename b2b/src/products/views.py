from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from .models import Product
from .serializers import ProductSerializer


class ProductListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data.copy()
        data['seller_id'] = request.user.id

        serializer = ProductSerializer(data=data)

        if serializer.is_valid():
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