from django.urls import path

from .views import (
    SKUCreateView,
    SKUDetailView,
    SKUByProductView,
    SKUImageCreateView,
    SKUImageDetailView,
)

urlpatterns = [
    path("api/skus/create", SKUCreateView.as_view(), name="sku-create"),
    path("api/skus/<uuid:sku_id>", SKUDetailView.as_view(), name="sku-detail"),
    path("api/skus/by-product/<uuid:product_id>", SKUByProductView.as_view(), name="sku-by-product"),
    path("api/skus/<uuid:sku_id>/images", SKUImageCreateView.as_view(), name="sku-image-create"),
    path("api/skus/images/<uuid:image_id>", SKUImageDetailView.as_view(), name="sku-image-detail"),
]