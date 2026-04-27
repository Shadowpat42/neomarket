from django.urls import path
from .views import FavoritesView

urlpatterns = [
    path('api/v1/favorites', FavoritesView.as_view()),
]