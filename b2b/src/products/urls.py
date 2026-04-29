from django.urls import path
from .views import ProductListCreateView, ProductDetailView

urlpatterns = [
    path('api/v1/products', ProductListCreateView.as_view()),
    path('api/v1/products/<int:product_id>', ProductDetailView.as_view()),
]