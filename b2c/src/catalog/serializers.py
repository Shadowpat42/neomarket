from rest_framework import serializers


class ImageRefSerializer(serializers.Serializer):
    """Matches ImageRef in B2C OpenAPI: {id, url, ordering}."""

    id = serializers.UUIDField(allow_null=True, required=False, default=None)
    url = serializers.URLField()
    ordering = serializers.IntegerField(default=0)


class SKUCardSerializer(serializers.Serializer):
    """Matches CatalogSku in B2C OpenAPI."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    price = serializers.IntegerField()
    discount = serializers.IntegerField(default=0)
    image = serializers.URLField(allow_null=True, required=False, default=None)
    available_quantity = serializers.IntegerField()
    in_stock = serializers.BooleanField()
    characteristics = serializers.ListField(
        child=serializers.DictField(), default=list
    )


class ProductCardSerializer(serializers.Serializer):
    """
    Matches CatalogProductDetail (extends CatalogProductCard) in B2C OpenAPI.
    slug and status are pass-throughs from B2B.
    """

    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField(allow_blank=True, default="")
    description = serializers.CharField(default="")
    status = serializers.CharField(allow_blank=True, required=False, default="")
    min_price = serializers.IntegerField(allow_null=True)
    has_stock = serializers.BooleanField()
    images = ImageRefSerializer(many=True, default=list)
    characteristics = serializers.ListField(
        child=serializers.DictField(), default=list
    )
    skus = SKUCardSerializer(many=True)
