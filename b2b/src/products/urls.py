from django.urls import path
from .views import (
    ProductListCreateView,
    ProductDetailView,
    ProductListView,
    ProductCatalogView,
    CategoryListCreateView,
    CategoryDetailView,
    ModerationEventView,
)

urlpatterns = [
    # Seller cabinet (Bearer JWT required)
    path('api/v1/products/', ProductListCreateView.as_view(), name='product-list-create'),
    path('api/v1/products/<uuid:product_id>/', ProductDetailView.as_view(), name='product-detail'),
    path('api/v1/products/my', ProductListView.as_view(), name='product-list'),

    # B2C public catalog (X-Service-Key required, no JWT)
    path('api/v1/public/products/', ProductCatalogView.as_view(), name='product-catalog'),

    path('api/categories', CategoryListCreateView.as_view(), name='category-list-create'),
    path('api/categories/<uuid:category_id>', CategoryDetailView.as_view(), name='category-detail'),

    # Moderation Service → B2B events (X-Service-Key required)
    path('api/v1/moderation/events', ModerationEventView.as_view(), name='moderation-events'),
]