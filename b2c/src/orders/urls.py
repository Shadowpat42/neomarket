from django.urls import path
from .views import OrdersView, OrderDetailView, CancelOrderView, ProductEventView

urlpatterns = [
    # US-ORD-02 + checkout: GET=list, POST=checkout
    path("api/v1/orders", OrdersView.as_view(), name="orders"),
    # US-ORD-02: order details with fixed prices
    path("api/v1/orders/<uuid:order_id>", OrderDetailView.as_view(), name="order-detail"),
    # US-ORD-03: cancel
    path("api/v1/orders/<uuid:order_id>/cancel", CancelOrderView.as_view(), name="order-cancel"),
    # US-ORD-04: incoming product events from B2B
    path("api/v1/events/product", ProductEventView.as_view(), name="product-event"),
]