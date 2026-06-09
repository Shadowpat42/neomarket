from django.urls import path

from .views import ProductListView, ProductCardView, FacetsView

urlpatterns = [
    path(
        "api/v1/catalog/products",
        ProductListView.as_view(),
        name="catalog-products",
    ),
    path(
        "api/v1/catalog/products/<uuid:product_id>",
        ProductCardView.as_view(),
        name="product-card",
    ),
    path(
        "api/v1/catalog/facets",
        FacetsView.as_view(),
        name="catalog-facets",
    ),
]