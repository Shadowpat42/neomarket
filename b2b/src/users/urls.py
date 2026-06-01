from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, CustomTokenObtainPairView, LogoutView, ProfileRetrieveView, ProfileUpdateView, ProfileDeleteView

urlpatterns = [
    # Auth
    path('api/v1/auth/register', RegisterView.as_view(), name='auth_register'),
    path('api/v1/auth/login', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/refresh', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/auth/logout', LogoutView.as_view(), name='auth_logout'),

    # Seller profile
    path('api/v1/seller/profile', ProfileRetrieveView.as_view(), name='seller_profile'),
    path('api/v1/seller/profile/update', ProfileUpdateView.as_view(), name='seller_profile_update'),
    path('api/v1/seller/profile/delete', ProfileDeleteView.as_view(), name='seller_profile_delete'),
]