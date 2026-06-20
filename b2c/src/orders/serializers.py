from rest_framework import serializers
from .models import Order, OrderItem


class CheckoutSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=255)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product_id",
            "sku_id",
            "product_title",
            "sku_name",
            "quantity",
            "unit_price",
            "line_total",
        ]


class OrderSerializer(serializers.ModelSerializer):
    """Internal serializer — used by checkout/cancel responses."""

    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user_id",
            "idempotency_key",
            "status",
            "total_amount",
            "cancel_reason",
            "cancelled_at",
            "items",
            "created_at",
            "updated_at",
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """Brief order representation for GET /api/v1/orders list."""

    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ["id", "status", "total_amount", "items_count", "created_at", "updated_at"]

    def get_items_count(self, obj: Order) -> int:
        return obj.items.count()


class OrderDetailSerializer(serializers.ModelSerializer):
    """Full order with items — GET /api/v1/orders/{id}. Prices from OrderItem, not B2B."""

    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "status",
            "items",
            "total_amount",
            "delivery_address",
            "created_at",
            "updated_at",
        ]