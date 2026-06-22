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

    buyer_id = serializers.UUIDField(source="user_id", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "buyer_id",
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

    buyer_id = serializers.UUIDField(source="user_id", read_only=True)
    subtotal = serializers.IntegerField(source="total_amount", read_only=True)
    total = serializers.IntegerField(source="total_amount", read_only=True)
    address = serializers.CharField(source="delivery_address", read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "buyer_id",
            "status",
            "items",
            "subtotal",
            "total",
            "address",
            "created_at",
            "updated_at",
        ]