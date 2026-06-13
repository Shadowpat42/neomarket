from django.urls import path

from .views import (
    SKUCreateView,
    SKUDetailView,
    SKUByProductView,
    SKUImageCreateView,
    SKUImageDetailView,
    ReserveView,
    UnreserveView,
)

urlpatterns = [
    path("api/skus/create", SKUCreateView.as_view(), name="sku-create"),
    path("api/v1/skus", SKUCreateView.as_view(), name="sku-create-v1"),
    path("api/v1/skus/<uuid:sku_id>", SKUDetailView.as_view(), name="sku-detail-v1"),
    path("api/skus/<uuid:sku_id>", SKUDetailView.as_view(), name="sku-detail"),
    path("api/skus/by-product/<uuid:product_id>", SKUByProductView.as_view(), name="sku-by-product"),
    path("api/skus/<uuid:sku_id>/images", SKUImageCreateView.as_view(), name="sku-image-create"),
    path("api/skus/images/<uuid:image_id>", SKUImageDetailView.as_view(), name="sku-image-detail"),

    # Inventory (B2C service-to-service)
    path("api/v1/inventory/reserve", ReserveView.as_view(), name="inventory-reserve"),
    path("api/v1/inventory/unreserve", UnreserveView.as_view(), name="inventory-unreserve"),
]