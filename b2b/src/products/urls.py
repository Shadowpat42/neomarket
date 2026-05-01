from django.urls import path
from .views import ProductListCreateView, ProductDetailView

urlpatterns = [
    path('api/v1/products/', ProductListCreateView.as_view(), name='product-list-create'),
    path('api/v1/products/<uuid:product_id>/', ProductDetailView.as_view(), name='product-detail'),
]