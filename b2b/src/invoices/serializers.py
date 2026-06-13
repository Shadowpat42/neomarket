from rest_framework import serializers

from .models import Invoice, InvoiceItem


class InvoiceItemCreateSerializer(serializers.Serializer):
    sku_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class InvoiceCreateSerializer(serializers.Serializer):
    items = InvoiceItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        return value


class InvoiceItemResponseSerializer(serializers.ModelSerializer):
    sku_id = serializers.UUIDField(source="sku.id", read_only=True)
    sku_name = serializers.CharField(source="sku.name", read_only=True)

    class Meta:
        model = InvoiceItem
        fields = ["id", "sku_id", "sku_name", "quantity", "accepted_quantity"]


class InvoiceResponseSerializer(serializers.ModelSerializer):
    items = InvoiceItemResponseSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "seller_id",
            "status",
            "items",
            "created_at",
            "updated_at",
            "accepted_at",
            "accepted_by",
        ]
