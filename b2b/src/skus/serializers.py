from rest_framework import serializers

from products.models import Product
from .models import SKU, SKUImage, SKUCharacteristic


class SKUImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUImage
        fields = ["id", "url", "ordering"]
        read_only_fields = ["id"]


class SKUCharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUCharacteristic
        fields = ["id", "name", "value"]
        read_only_fields = ["id"]


class SKUSerializer(serializers.ModelSerializer):
    images = SKUImageSerializer(many=True, required=False)
    characteristics = SKUCharacteristicSerializer(many=True, required=False)
    product_id = serializers.UUIDField(write_only=True, required=True)

    class Meta:
        model = SKU
        fields = [
            "id",
            "product_id",
            "product",
            "name",
            "price",
            "stock_quantity",
            "article",
            "images",
            "characteristics",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "product", "created_at", "updated_at"]

    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        characteristics_data = validated_data.pop("characteristics", [])
        product_id = validated_data.pop("product_id")

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            raise serializers.ValidationError(
                {"product_id": "Товар с таким ID не существует"}
            )

        sku = SKU.objects.create(product=product, **validated_data)

        for image_data in images_data:
            SKUImage.objects.create(sku=sku, **image_data)

        for characteristic_data in characteristics_data:
            SKUCharacteristic.objects.create(sku=sku, **characteristic_data)

        return sku

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        characteristics_data = validated_data.pop("characteristics", None)
        validated_data.pop("product_id", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if images_data is not None:
            instance.images.all().delete()
            for image_data in images_data:
                SKUImage.objects.create(sku=instance, **image_data)

        if characteristics_data is not None:
            instance.characteristics.all().delete()
            for characteristic_data in characteristics_data:
                SKUCharacteristic.objects.create(sku=instance, **characteristic_data)

        return instance


class SKUUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKU
        fields = ["name", "price", "article"]


class SKUImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUImage
        fields = ["url", "ordering"]