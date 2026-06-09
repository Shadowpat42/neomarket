from django.contrib import admin
from .models import CartItem


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user_id", "session_id", "product_id", "sku_id", "quantity")
    search_fields = ("user_id", "session_id", "product_id", "sku_id")