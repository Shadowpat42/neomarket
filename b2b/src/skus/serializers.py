from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied

from products.models import Product
from .models import SKU, SKUImage, SKUCharacteristic
from .moderation import send_product_event
from .services import resolve_sku_create_side_effects


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


class SKUCharacteristicInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    value = serializers.CharField(max_length=255)


class SKUCharacteristicCreateResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUCharacteristic
        fields = ["name", "value"]


class SKUCreateResponseSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    image = serializers.SerializerMethodField()
    active_quantity = serializers.IntegerField(read_only=True)
    characteristics = SKUCharacteristicCreateResponseSerializer(many=True, read_only=True)

    class Meta:
        model = SKU
        fields = [
            "id",
            "product_id",
            "name",
            "price",
            "cost_price",
            "discount",
            "image",
            "active_quantity",
            "reserved_quantity",
            "characteristics",
        ]

    def get_image(self, obj):
        first_image = obj.images.order_by("ordering").first()
        return first_image.url if first_image else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["product_id"] = str(instance.product_id)
        data["active_quantity"] = instance.active_quantity
        return data


class SKUCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    name = serializers.CharField(max_length=255)
    price = serializers.IntegerField()
    cost_price = serializers.IntegerField()
    discount = serializers.IntegerField(required=False, default=0, min_value=0)
    image = serializers.CharField(
        error_messages={
            "required": "image is required",
            "blank": "image is required",
        }
    )
    characteristics = SKUCharacteristicInputSerializer(many=True, required=False, default=list)

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("name is required")
        return value.strip()

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "price must be a positive integer (kopecks)"
            )
        return value

    def validate_cost_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "cost_price must be a positive integer (kopecks)"
            )
        return value

    def validate_image(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("image is required")
        return value.strip()

    def validate(self, attrs):
        try:
            product = Product.objects.get(id=attrs["product_id"])
        except Product.DoesNotExist:
            raise NotFound("Product not found")

        request = self.context.get("request")
        if request and product.seller_id != request.user.id:
            raise PermissionDenied("У вас нет доступа к этому товару")

        attrs["product"] = product
        return attrs

    def create(self, validated_data):
        product = validated_data.pop("product")
        image_url = validated_data.pop("image")
        characteristics_data = validated_data.pop("characteristics", [])
        validated_data.pop("product_id")

        is_first_sku = not product.skus.exists()
        previous_status = product.status

        event_type = resolve_sku_create_side_effects(
            product,
            is_first_sku=is_first_sku,
            previous_status=previous_status,
        )

        sku = SKU.objects.create(product=product, **validated_data)
        SKUImage.objects.create(sku=sku, url=image_url, ordering=0)

        for characteristic_data in characteristics_data:
            SKUCharacteristic.objects.create(sku=sku, **characteristic_data)

        if event_type:
            send_product_event(product, event_type)

        return sku


class SKUSerializer(serializers.ModelSerializer):
    images = SKUImageSerializer(many=True, required=False)
    characteristics = SKUCharacteristicSerializer(many=True, required=False)
    product_id = serializers.UUIDField(write_only=True, required=True)
    active_quantity = serializers.IntegerField(read_only=True)

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "active_quantity", "created_at", "updated_at"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["product_id"] = str(instance.product_id)
        data["active_quantity"] = instance.active_quantity
        return data

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

        request = self.context.get("request")
        if request and product.seller_id != request.user.id:
            raise PermissionDenied("У вас нет доступа к этому товару")

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


class SKUImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKUImage
        fields = ["url", "ordering"]
