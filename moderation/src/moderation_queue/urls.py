from django.urls import path
from .views import GetNextProductView

urlpatterns = [
    path('api/v1/product-moderation/get-next', GetNextProductView.as_view()),
]