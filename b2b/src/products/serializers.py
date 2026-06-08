from django.utils.text import slugify
from rest_framework import serializers
from .models import (
    Product,
    Image,
    Characteristic,
    Category,
    BaseProductStatus,
    BlockingReason,
    ProductFieldReport,
)
from skus.serializers import SKUSerializer
from skus.models import SKU


class ImageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = Image
        fields = ["id", "url", "ordering"]


class CharacteristicSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="uuid", read_only=True)

    class Meta:
        model = Characteristic
        fields = ["id", "name", "value"]


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
    description = serializers.CharField(required=True,min_length=1,max_length=5000)
    images = ImageSerializer(many=True, required=True)
    characteristics = CharacteristicSerializer(many=True, required=False)
    category_id = serializers.UUIDField(error_messages={"invalid": "category_id must be a valid UUID"})
    skus = SKUSerializer(many=True, read_only=True)
    slug = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "seller_id",
            "category_id",
            "title",
            "slug",
            "description",
            "status",
            "deleted",
            "blocking_reason_id",
            "moderator_comment",
            "images",
            "characteristics",
            "created_at",
            "updated_at",
            "skus",
        ]
        read_only_fields = [
            "id",
            "seller_id",
            "status",
            "created_at",
            "updated_at",
        ]
    
    def validate_title(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("title is required")

        if len(value) > 255:
            raise serializers.ValidationError(
                "title must be 1-255 characters"
            )

        return value

    def validate_images(self, value):
        if not value or len(value) == 0:
            raise serializers.ValidationError(
                "At least one image is required"
            )

        return value

    def validate_category_id(self, value):
        if not Category.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                "Category not found"
            )

        return value

    def create(self, validated_data):
        images_data = validated_data.pop("images")
        characteristics_data = validated_data.pop(
            "characteristics",
            []
        )

        category_id = validated_data.pop("category_id")
        category = Category.objects.get(id=category_id)

        slug_value = validated_data.get("slug") or ""
        if not slug_value.strip():
            validated_data["slug"] = slugify(validated_data.get("title", ""))[:255]

        product = Product.objects.create(
            category=category,
            status=BaseProductStatus.CREATED,
            **validated_data
        )

        Image.objects.bulk_create([
            Image(product=product, **image_data)
            for image_data in images_data
        ])

        Characteristic.objects.bulk_create([
            Characteristic(product=product, **char_data)
            for char_data in characteristics_data
        ])

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
                raise serializers.ValidationError({"category_id": "Category not found"})
            

        slug_value = validated_data.get("slug", None)
        if slug_value is not None and not (slug_value or "").strip():
            validated_data["slug"] = slugify(validated_data.get("title", instance.title))[:255]

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


class ProductCategoryBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ProductDetailImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        fields = ["url", "ordering"]


class ProductDetailCharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Characteristic
        fields = ["name", "value"]


class ProductDetailSKUCharacteristicSerializer(serializers.Serializer):
    name = serializers.CharField()
    value = serializers.CharField()


class ProductDetailSKUSerializer(serializers.ModelSerializer):
    """SKU в seller cabinet (B2B-5): одно поле image, cost_price, reserved_quantity."""

    image = serializers.SerializerMethodField()
    characteristics = ProductDetailSKUCharacteristicSerializer(many=True, read_only=True)
    active_quantity = serializers.SerializerMethodField()

    class Meta:
        model = SKU
        fields = [
            "id",
            "name",
            "price",
            "cost_price",
            "discount",
            "image",
            "active_quantity",
            "reserved_quantity",
            "characteristics",
        ]

    def get_image(self, obj: SKU) -> str | None:
        first = obj.images.order_by("ordering").first()
        return first.url if first else None

    def get_active_quantity(self, obj: SKU) -> int:
        reserved = obj.reserved_quantity or 0
        stock = obj.stock_quantity or 0
        return max(0, stock - reserved)


class FieldReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductFieldReport
        fields = ["field_name", "sku_id", "comment"]


class BlockingReasonDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    comment = serializers.CharField()


# ── B2C public catalog serializers (no cost_price / no reserved_quantity) ──


class PublicSKUCharacteristicSerializer(serializers.ModelSerializer):
    class Meta:
        model = SKU.characteristics.field.related_model
        fields = ["name", "value"]


class PublicSKUSerializer(serializers.ModelSerializer):
    """
    B2C vitrine SKU: excludes cost_price and reserved_quantity.
    """

    image = serializers.SerializerMethodField()
    characteristics = serializers.SerializerMethodField()
    active_quantity = serializers.SerializerMethodField()

    class Meta:
        model = SKU
        fields = [
            "id",
            "name",
            "price",
            "discount",
            "image",
            "active_quantity",
            "characteristics",
        ]

    def get_image(self, obj: SKU) -> str | None:
        first = obj.images.order_by("ordering").first()
        return first.url if first else None

    def get_active_quantity(self, obj: SKU) -> int:
        return max(0, (obj.stock_quantity or 0) - (obj.reserved_quantity or 0))

    def get_characteristics(self, obj: SKU) -> list:
        return [{"name": c.name, "value": c.value} for c in obj.characteristics.all()]


class PublicProductSerializer(serializers.ModelSerializer):
    """
    B2C vitrine product: no blocking/moderation fields, no cost_price.
    Matches ProductPublicShortResponse in OpenAPI (includes min_price).
    """

    category = ProductCategoryBriefSerializer(read_only=True)
    images = ProductDetailImageSerializer(many=True, read_only=True)
    characteristics = ProductDetailCharacteristicSerializer(many=True, read_only=True)
    skus = PublicSKUSerializer(many=True, read_only=True)
    min_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "seller_id",
            "category_id",
            "title",
            "slug",
            "description",
            "status",
            "min_price",
            "category",
            "images",
            "characteristics",
            "skus",
            "created_at",
            "updated_at",
        ]

    def get_min_price(self, obj: Product) -> int | None:
        prices = [sku.price for sku in obj.skus.all() if sku.price is not None]
        return min(prices) if prices else None


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Seller cabinet: GET /api/v1/products/{id} (B2B-5 / ProductDetailResponse).
    """

    category = ProductCategoryBriefSerializer(read_only=True)
    images = ProductDetailImageSerializer(many=True, read_only=True)
    characteristics = ProductDetailCharacteristicSerializer(many=True, read_only=True)
    skus = ProductDetailSKUSerializer(many=True, read_only=True)
    blocked = serializers.SerializerMethodField()
    blocking_reason = serializers.SerializerMethodField()
    field_reports = FieldReportSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "seller_id",
            "category_id",
            "title",
            "slug",
            "description",
            "status",
            "deleted",
            "blocked",
            "category",
            "images",
            "characteristics",
            "skus",
            "blocking_reason",
            "field_reports",
            "created_at",
            "updated_at",
        ]

    def get_blocked(self, obj: Product) -> bool:
        return obj.status in {
            BaseProductStatus.BLOCKED,
            BaseProductStatus.HARD_BLOCKED,
        }

    def get_blocking_reason(self, obj: Product):
        if not obj.blocking_reason_id:
            return None

        try:
            reason = BlockingReason.objects.get(id=obj.blocking_reason_id)
        except BlockingReason.DoesNotExist:
            return None

        return {
            "id": reason.id,
            "title": reason.title,
            "comment": obj.moderator_comment or "",
        }