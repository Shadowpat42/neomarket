from django.conf import settings
from rest_framework.permissions import BasePermission


class IsSellerOrServiceKey(BasePermission):
    """
    Seller cabinet: Bearer JWT.
    Inter-service (Moderation): valid X-Service-Key header.
    """

    def has_permission(self, request, view):
        service_key = request.headers.get("X-Service-Key")
        if service_key and service_key == settings.B2B_SERVICE_KEY:
            return True
        return bool(request.user and request.user.is_authenticated)
