import logging

from django.contrib import admin

from .models import Order, OrderItem

logger = logging.getLogger(__name__)


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
    actions = ["mark_as_delivered"]

    @admin.action(description="Отметить как DELIVERED и выполнить fulfill к B2B")
    def mark_as_delivered(self, request, queryset):
        from .views import deliver_order

        eligible = queryset.filter(status="DELIVERING")
        for order in eligible:
            deliver_order(order)
        skipped = queryset.count() - eligible.count()
        self.message_user(
            request,
            f"DELIVERED: {eligible.count()} заказ(ов). Пропущено (статус ≠ DELIVERING): {skipped}.",
        )