from rest_framework import serializers


class SKUCardSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    article = serializers.CharField()
    price = serializers.IntegerField()
    discount = serializers.IntegerField()
    active_quantity = serializers.IntegerField()
    in_stock = serializers.BooleanField()


class ProductCardSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    images = serializers.ListField()
    characteristics = serializers.ListField()
    skus = SKUCardSerializer(many=True)