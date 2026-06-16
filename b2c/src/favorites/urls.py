from django.urls import path

from .views import FavoritesListView, FavoriteItemView, SubscribeView

urlpatterns = [
    # US-CART-01: Favorites CRUD
    path("api/v1/favorites", FavoritesListView.as_view(), name="favorites-list"),
    path(
        "api/v1/favorites/<uuid:product_id>",
        FavoriteItemView.as_view(),
        name="favorite-item",
    ),
    # US-CART-02: Subscriptions
    path(
        "api/v1/favorites/<uuid:product_id>/subscribe",
        SubscribeView.as_view(),
        name="favorite-subscribe",
    ),
]
