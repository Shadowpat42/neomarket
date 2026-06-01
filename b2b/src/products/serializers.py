from django.utils.text import slugify
from rest_framework import serializers

from .models import Product, Image, Characteristic, Category
from skus.serializers import SKUSerializer


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ["id", "url", "ordering"]
        read_only_fields = ["id"]


class CharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Characteristic
        fields = ["id", "name", "value"]
        read_only_fields = ["id"]


class CategorySerializer(serializers.ModelSerializer):
    parent_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Category
        fields = ["id", "name", "parent", "parent_id", "created_at"]
        read_only_fields = ["id", "parent", "created_at"]

    def create(self, validated_data):
        parent_id = validated_data.pop("parent_id", None)

        parent = None
        if parent_id:
            try:
                parent = Category.objects.get(id=parent_id)
            except Category.DoesNotExist:
                raise serializers.ValidationError(
                    {"parent_id": "Родительская категория не найдена"}
                )

        return Category.objects.create(parent=parent, **validated_data)


class ProductSerializer(serializers.ModelSerializer):
    images = ImageSerializer(many=True, required=True)
    characteristics = CharacteristicSerializer(many=True, required=False)
    skus = SKUSerializer(many=True, read_only=True)

    category_id = serializers.UUIDField(
        write_only=True,
        required=True,
        error_messages={
            "invalid": "category_id must be a valid UUID"
        }
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "seller_id",
            "slug",
            "title",
            "description",
            "status",
            "deleted",
            "blocking_reason_id",
            "moderator_comment",
            "category_id",
            "images",
            "characteristics",
            "skus",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "seller_id",
            "slug",
            "status",
            "deleted",
            "blocking_reason_id",
            "moderator_comment",
            "created_at",
            "updated_at",
            "skus",
        ]

    def validate_images(self, value):
        if not value:
            raise serializers.ValidationError("At least one image is required")
        return value

    def validate_category_id(self, value):
        if not Category.objects.filter(id=value).exists():
            raise serializers.ValidationError("Category not found")
        return value

    def create(self, validated_data):
        images_data = validated_data.pop("images")
        characteristics_data = validated_data.pop("characteristics", [])
        category_id = validated_data.pop("category_id")

        category = Category.objects.get(id=category_id)

        base_slug = slugify(validated_data.get("title", "")) or "product"
        slug = base_slug
        counter = 1

        while Product.objects.filter(slug=slug).exists():
            counter += 1
            slug = f"{base_slug}-{counter}"

        product = Product.objects.create(
            category=category,
            slug=slug,
            **validated_data,
        )

        for image_data in images_data:
            Image.objects.create(product=product, **image_data)

        for characteristic_data in characteristics_data:
            Characteristic.objects.create(product=product, **characteristic_data)

        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        characteristics_data = validated_data.pop("characteristics", None)
        category_id = validated_data.pop("category_id", None)

        if category_id:
            try:
                instance.category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                raise serializers.ValidationError({"category_id": "Category not found"})

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