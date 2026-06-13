from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied

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
    # Canon flow uses `image` (single url). OpenAPI uses `images` (array).
    # We accept both for backwards compatibility.
    image = serializers.URLField(write_only=True, required=False)
    characteristics = SKUCharacteristicSerializer(many=True, required=False)

    product_id = serializers.UUIDField(required=True)
    name = serializers.CharField(required=True, max_length=255, allow_blank=True)
    price = serializers.IntegerField(required=True)
    cost_price = serializers.IntegerField(required=True)
    discount = serializers.IntegerField(required=False, min_value=0, default=0)

    active_quantity = serializers.SerializerMethodField()

    class Meta:
        model = SKU
        fields = [
            "id",
            "product_id",
            "name",
            "price",
            "discount",
            "cost_price",
            "stock_quantity",
            "active_quantity",
            "reserved_quantity",
            "article",
            "images",
            "characteristics",
            "image",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "active_quantity"]

    def get_active_quantity(self, obj: SKU) -> int:
        reserved = obj.reserved_quantity or 0
        stock = obj.stock_quantity or 0
        return max(0, stock - reserved)

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise NotFound("Product not found")

        request = self.context.get("request")
        if product.status == "HARD_BLOCKED":
            raise PermissionDenied("Cannot add SKU to hard-blocked product")

        if request is not None and str(product.seller_id) != str(request.user.id):
            raise PermissionDenied("У вас нет прав на этот товар")

        return value

    def validate(self, attrs):
        images_data = attrs.get("images") or []
        image_url = attrs.pop("image", None)

        name = attrs.get("name")
        if not name or not str(name).strip():
            raise serializers.ValidationError({"name": "name is required"})

        price = attrs.get("price")
        if price is None or int(price) <= 0:
            raise serializers.ValidationError(
                {"price": "price must be a positive integer (kopecks)"}
            )

        cost_price = attrs.get("cost_price")
        if cost_price is None or int(cost_price) <= 0:
            raise serializers.ValidationError(
                {"cost_price": "cost_price must be a positive integer (kopecks)"}
            )

        if not images_data and image_url:
            images_data = [{"url": image_url, "ordering": 0}]

        if not images_data:
            raise serializers.ValidationError({"image": "image is required"})

        attrs["images"] = images_data
        return attrs

    def create(self, validated_data):
        images_data = validated_data.pop("images", [])
        characteristics_data = validated_data.pop("characteristics", [])
        product_id = validated_data.pop("product_id")
        product = Product.objects.get(id=product_id)

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
        fields = ["name", "price", "discount", "cost_price", "article"]


class SKUPutSerializer(serializers.Serializer):
    """
    Full replacement serializer for PUT /api/v1/skus/{id}.
    Like POST /skus but without product_id; reserved_quantity is never touched.
    """

    name = serializers.CharField(required=True, max_length=255)
    price = serializers.IntegerField(required=True, min_value=1)
    cost_price = serializers.IntegerField(required=True, min_value=1)
    discount = serializers.IntegerField(required=False, min_value=0, default=0)
    image = serializers.URLField(write_only=True, required=False)
    images = SKUImageSerializer(many=True, required=False)
    characteristics = SKUCharacteristicSerializer(many=True, required=False)

    def validate(self, attrs):
        images_data = list(attrs.get("images") or [])
        image_url = attrs.pop("image", None)

        if not images_data and image_url:
            images_data = [{"url": image_url, "ordering": 0}]
        if not images_data:
            raise serializers.ValidationError({"image": "image is required"})

        attrs["images"] = images_data
        return attrs

    def update(self, instance, validated_data):
        images_data = validated_data.pop("images", None)
        characteristics_data = validated_data.pop("characteristics", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if images_data is not None:
            instance.images.all().delete()
            for img in images_data:
                SKUImage.objects.create(sku=instance, **img)

        if characteristics_data is not None:
            instance.characteristics.all().delete()
            for char in characteristics_data:
                SKUCharacteristic.objects.create(sku=instance, **char)

        return instance


class SKUImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUImage
        fields = ["url", "ordering"]