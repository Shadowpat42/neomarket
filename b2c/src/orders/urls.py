from django.urls import path
from .views import CheckoutView

urlpatterns = [
    path("api/v1/orders", CheckoutView.as_view(), name="checkout"),
]