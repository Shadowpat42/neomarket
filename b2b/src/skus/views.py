from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from products.models import Product
from .models import SKU, SKUImage
from .serializers import (
    SKUSerializer,
    SKUUpdateSerializer,
    SKUImageSerializer,
    SKUImageUpdateSerializer,
)


class SKUCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        product_id = request.data.get("product_id")

        product = Product.objects.filter(id=product_id).first()

        if product is None:
            return Response(
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if product.seller_id != request.user.id:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "Нет прав на создание SKU для этого товара",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SKUSerializer(data=request.data)

        if serializer.is_valid():
            sku = serializer.save()
            return Response(SKUSerializer(sku).data, status=status.HTTP_201_CREATED)

        return Response(
            {
                "code": "INVALID_SKU_DATA",
                "message": "Некорректные данные SKU",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


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

        if sku.product.seller_id != request.user.id:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "Нет прав на изменение этого SKU",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SKUUpdateSerializer(sku, data=request.data, partial=True)

        if serializer.is_valid():
            sku = serializer.save()
            return Response(SKUSerializer(sku).data, status=status.HTTP_200_OK)

        return Response(
            {
                "code": "INVALID_SKU_DATA",
                "message": "Некорректные данные SKU",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

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

        if sku.product.seller_id != request.user.id:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "Нет прав на удаление этого SKU",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        sku.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SKUByProductView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        product = Product.objects.filter(id=product_id).first()

        if product is None:
            return Response(
                {
                    "code": "PRODUCT_NOT_FOUND",
                    "message": "Товар не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        skus = SKU.objects.filter(product=product).prefetch_related(
            "images",
            "characteristics",
        )

        return Response(SKUSerializer(skus, many=True).data, status=status.HTTP_200_OK)


class SKUImageCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, sku_id):
        sku = SKU.objects.select_related("product").filter(id=sku_id).first()

        if sku is None:
            return Response(
                {
                    "code": "SKU_NOT_FOUND",
                    "message": "SKU не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if sku.product.seller_id != request.user.id:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "Нет прав на добавление изображения к этому SKU",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SKUImageSerializer(data=request.data)

        if serializer.is_valid():
            image = serializer.save(sku=sku)
            return Response(SKUImageSerializer(image).data, status=status.HTTP_201_CREATED)

        return Response(
            {
                "code": "INVALID_SKU_IMAGE_DATA",
                "message": "Некорректные данные изображения SKU",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class SKUImageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, image_id):
        try:
            return SKUImage.objects.select_related("sku__product").get(id=image_id)
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

        if image.sku.product.seller_id != request.user.id:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "Нет прав на изменение изображения этого SKU",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SKUImageUpdateSerializer(image, data=request.data, partial=True)

        if serializer.is_valid():
            image = serializer.save()
            return Response(SKUImageSerializer(image).data, status=status.HTTP_200_OK)

        return Response(
            {
                "code": "INVALID_SKU_IMAGE_DATA",
                "message": "Некорректные данные изображения SKU",
                "details": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

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

        if image.sku.product.seller_id != request.user.id:
            return Response(
                {
                    "code": "FORBIDDEN",
                    "message": "Нет прав на удаление изображения этого SKU",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)