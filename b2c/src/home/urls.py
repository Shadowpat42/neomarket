from django.urls import path

from .views import (
    BannerListView,
    BannerEventView,
    CollectionsListView,
    CollectionProductsView,
)

urlpatterns = [
    # US-CART-04: Banners
    path("api/v1/home/banners", BannerListView.as_view(), name="home-banners"),
    path("api/v1/banner-events", BannerEventView.as_view(), name="banner-events"),
    # US-CART-05: Collections
    path("api/v1/main/collections", CollectionsListView.as_view(), name="collections-list"),
    path(
        "api/v1/collections/<uuid:collection_id>/products",
        CollectionProductsView.as_view(),
        name="collection-products",
    ),
]
