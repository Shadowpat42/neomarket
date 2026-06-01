from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from products.models import Product
from .models import SKU, SKUImage
from .serializers import (
    SKUCreateSerializer,
    SKUCreateResponseSerializer,
    SKUSerializer,
    SKUUpdateSerializer,
    SKUImageSerializer,
    SKUImageUpdateSerializer,
)


def _first_validation_message(errors):
    first_value = next(iter(errors.values()))
    if isinstance(first_value, list):
        return str(first_value[0])
    return str(first_value)


class SKUCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SKUCreateSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            sku = serializer.save()
            return Response(
                SKUCreateResponseSerializer(sku).data,
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "code": "INVALID_REQUEST",
                "message": _first_validation_message(serializer.errors),
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
                    "code": "NOT_FOUND",
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
                    "code": "NOT_FOUND",
                    "message": "SKU не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SKUUpdateSerializer(sku, data=request.data, partial=True)

        if serializer.is_valid():
            sku = serializer.save()
            return Response(SKUSerializer(sku).data, status=status.HTTP_200_OK)

        return Response(
            {
                "code": "INVALID_REQUEST",
                "message": _first_validation_message(serializer.errors),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, sku_id):
        sku = self.get_object(sku_id)

        if sku is None:
            return Response(
                {
                    "code": "NOT_FOUND",
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
                    "code": "NOT_FOUND",
                    "message": "Product not found",
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
                    "code": "NOT_FOUND",
                    "message": "SKU не найден",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SKUImageSerializer(data=request.data)

        if serializer.is_valid():
            image = serializer.save(sku=sku)
            return Response(SKUImageSerializer(image).data, status=status.HTTP_201_CREATED)

        return Response(
            {
                "code": "INVALID_REQUEST",
                "message": _first_validation_message(serializer.errors),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


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
                    "code": "NOT_FOUND",
                    "message": "Изображение SKU не найдено",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SKUImageUpdateSerializer(image, data=request.data, partial=True)

        if serializer.is_valid():
            image = serializer.save()
            return Response(SKUImageSerializer(image).data, status=status.HTTP_200_OK)

        return Response(
            {
                "code": "INVALID_REQUEST",
                "message": _first_validation_message(serializer.errors),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request, image_id):
        image = self.get_object(image_id)

        if image is None:
            return Response(
                {
                    "code": "NOT_FOUND",
                    "message": "Изображение SKU не найдено",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
