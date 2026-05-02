from django.urls import path
from .views import (
    ProductListCreateView,
    ProductDetailView,
    ProductListView,
    CategoryListCreateView,
    CategoryDetailView,
)

urlpatterns = [
    path('api/v1/products/', ProductListCreateView.as_view(), name='product-list-create'),
    path('api/v1/products/<uuid:product_id>/', ProductDetailView.as_view(), name='product-detail'),
    path('api/v1/products/my', ProductListView.as_view(), name='product-list'),

    path('api/categories', CategoryListCreateView.as_view(), name='category-list-create'),
    path('api/categories/<uuid:category_id>', CategoryDetailView.as_view(), name='category-detail'),
]