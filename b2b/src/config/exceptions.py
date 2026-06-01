from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.views import exception_handler

STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


def _first_message(detail):
    if isinstance(detail, list):
        return str(detail[0])
    if isinstance(detail, dict):
        first_value = next(iter(detail.values()))
        return _first_message(first_value)
    return str(detail)


def _error_code(exc, status_code):
    if isinstance(exc, ValidationError):
        return "VALIDATION_ERROR"
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return "UNAUTHORIZED"
    if isinstance(exc, PermissionDenied):
        return "FORBIDDEN"
    if isinstance(exc, NotFound):
        return "NOT_FOUND"

    default_code = getattr(exc, "default_code", None)
    if default_code:
        return str(default_code).upper()

    return STATUS_CODES.get(status_code, "ERROR")


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return None

    if 400 <= response.status_code < 500:
        message = _first_message(exc.detail) if hasattr(exc, "detail") else "Request error"
        payload = {
            "code": _error_code(exc, response.status_code),
            "message": message,
        }

        if isinstance(exc, ValidationError) and isinstance(exc.detail, dict):
            payload["details"] = exc.detail

        response.data = payload

    return response
