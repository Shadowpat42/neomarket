from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _first_error_message(details: Any) -> str:
    """
    Best-effort flatten for DRF ValidationError/serializer errors.
    Returns a single human-readable message string.
    """

    if details is None:
        return "Invalid request"

    # List of errors
    if isinstance(details, list):
        if not details:
            return "Invalid request"
        return _first_error_message(details[0])

    # Dict of field -> errors
    if isinstance(details, dict):
        if not details:
            return "Invalid request"
        first_value = next(iter(details.values()))
        return _first_error_message(first_value)

    return str(details)


def _code_for_status(http_status: int, exc: Exception) -> str:
    if http_status == status.HTTP_400_BAD_REQUEST:
        return "INVALID_REQUEST"
    if http_status == status.HTTP_401_UNAUTHORIZED:
        return "UNAUTHORIZED"
    if http_status == status.HTTP_403_FORBIDDEN:
        return "FORBIDDEN"
    if http_status == status.HTTP_404_NOT_FOUND:
        return "NOT_FOUND"
    if http_status == status.HTTP_409_CONFLICT:
        return "CONFLICT"
    if isinstance(exc, APIException) and getattr(exc, "default_code", None):
        return str(exc.default_code).upper()
    return "ERROR"


def api_exception_handler(exc: Exception, context: dict) -> Response | None:
    """
    Unified error format for all 4xx:
      {"code": "...", "message": "..."}
    """

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if 400 <= response.status_code < 500:
        return Response(
            {
                "code": _code_for_status(response.status_code, exc),
                "message": _first_error_message(getattr(response, "data", None)),
            },
            status=response.status_code,
            headers=getattr(response, "headers", None),
        )

    return response

