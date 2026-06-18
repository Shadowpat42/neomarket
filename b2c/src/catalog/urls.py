from django.urls import path

from .views import (
    ProductListView,
    ProductCardView,
    FacetsView,
    SimilarProductsView,
    CategoryFlatListView,
    CategoryTreeView,
    CategoryDetailView,
    BreadcrumbsView,
)

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
        "api/v1/catalog/products/<uuid:product_id>/similar",
        SimilarProductsView.as_view(),
        name="similar-products",
    ),
    path(
        "api/v1/catalog/facets",
        FacetsView.as_view(),
        name="catalog-facets",
    ),
    # US-CAT-05: категории и навигация
    path(
        "api/v1/catalog/categories",
        CategoryFlatListView.as_view(),
        name="category-flat",
    ),
    path(
        "api/v1/catalog/categories/tree",
        CategoryTreeView.as_view(),
        name="category-tree",
    ),
    path(
        "api/v1/catalog/categories/<uuid:category_id>",
        CategoryDetailView.as_view(),
        name="category-detail",
    ),
    path(
        "api/v1/breadcrumbs",
        BreadcrumbsView.as_view(),
        name="breadcrumbs",
    ),
]
