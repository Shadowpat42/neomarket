from django.urls import path
from .views import CheckoutView, CancelOrderView

urlpatterns = [
    path("api/v1/orders", CheckoutView.as_view(), name="checkout"),
    path("api/v1/orders/<uuid:order_id>/cancel", CancelOrderView.as_view(), name="order-cancel"),
]