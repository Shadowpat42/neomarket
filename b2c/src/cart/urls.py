from django.urls import path

from .views import (
    CartView,
    CartItemCreateView,
    CartItemDetailView,
    CartMergeView,
)

urlpatterns = [
    path("api/v1/cart", CartView.as_view(), name="cart"),
    path("api/v1/cart/items", CartItemCreateView.as_view(), name="cart-item-create"),
    path("api/v1/cart/items/<uuid:sku_id>", CartItemDetailView.as_view(), name="cart-item-detail"),
    path("api/v1/cart/merge", CartMergeView.as_view(), name="cart-merge"),
]