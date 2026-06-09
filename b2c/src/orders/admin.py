from django.contrib import admin
from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product_id",
        "sku_id",
        "product_title",
        "sku_name",
        "quantity",
        "unit_price",
        "line_total",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "status", "total_amount", "idempotency_key", "created_at")
    search_fields = ("id", "user_id", "idempotency_key")
    list_filter = ("status", "created_at")
    inlines = [OrderItemInline]