from rest_framework import serializers
from .models import Product, Image, Characteristic


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ["url", "ordering"]


class CharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Characteristic
        fields = ["name", "value"]


class ProductSerializer(serializers.ModelSerializer):
    images = ImageSerializer(many=True, required=False)
    characteristics = CharacteristicSerializer(many=True, required=False)
    category = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "description",
            "status",
            "category",
            "category_id",
            "category_name",
            "images",
            "characteristics",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def get_category(self, obj):
        return {
            "id": obj.category_id,
            "name": obj.category_name,
        }

    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        characteristics_data = validated_data.pop("characteristics", [])

        product = Product.objects.create(**validated_data)

        for image_data in images_data:
            Image.objects.create(product=product, **image_data)

        for characteristic_data in characteristics_data:
            Characteristic.objects.create(product=product, **characteristic_data)

        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        characteristics_data = validated_data.pop("characteristics", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if images_data is not None:
            instance.images.all().delete()
            for image_data in images_data:
                Image.objects.create(product=instance, **image_data)

        if characteristics_data is not None:
            instance.characteristics.all().delete()
            for characteristic_data in characteristics_data:
                Characteristic.objects.create(product=instance, **characteristic_data)

        return instance