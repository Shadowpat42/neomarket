from django.conf import settings
from rest_framework.permissions import BasePermission


class IsSellerOrServiceKey(BasePermission):
    """
    Seller cabinet: Bearer JWT.
    Inter-service (Moderation / B2B): valid X-Service-Key header.
    """

    def has_permission(self, request, view):
        service_key = request.headers.get("X-Service-Key")
        if service_key and service_key == settings.B2B_SERVICE_KEY:
            return True
        return bool(request.user and request.user.is_authenticated)


class IsB2CServiceKey(BasePermission):
    """
    B2C public catalog: requires X-Service-Key matching B2C_SERVICE_KEY.
    Bearer JWT is intentionally NOT accepted — prevents sellers from
    accessing the catalog mode to bypass seller_id ownership filters.
    """

    message = "Valid X-Service-Key required."

    def has_permission(self, request, view):
        service_key = request.headers.get("X-Service-Key")
        return bool(service_key and service_key == settings.B2C_SERVICE_KEY)
