from django.urls import path
from .views import ProductCardView

urlpatterns = [
    path(
        'api/v1/catalog/products/<uuid:product_id>',
        ProductCardView.as_view(),
        name='product-card'
    ),
]
