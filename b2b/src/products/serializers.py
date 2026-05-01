from rest_framework import serializers
from .models import Product, Image, Characteristic, Category    


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ["url", "ordering"]


class CharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Characteristic
        fields = ["name", "value"]


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ProductSerializer(serializers.ModelSerializer):
    images = ImageSerializer(many=True, required=False)
    characteristics = CharacteristicSerializer(many=True, required=False)
    category = CategorySerializer(read_only=True)
    category_id = serializers.UUIDField(write_only=True, required=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "description",
            "status",
            "category",
            "category_id",
            "images",
            "characteristics",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        characteristics_data = validated_data.pop("characteristics", [])
        category_id = validated_data.pop("category_id")

        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            raise serializers.ValidationError({"category_id": "Категория с таким ID не существует"})
        
        product = Product.objects.create(category=category, **validated_data)

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
                category = Category.objects.get(id=category_id)
                instance.category = category
            except Category.DoesNotExist:
                raise serializers.ValidationError({"category_id": "Категория с таким ID не существует"})
            

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