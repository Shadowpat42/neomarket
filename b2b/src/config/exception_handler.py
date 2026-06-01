from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return response

    detail = None
    if isinstance(response.data, dict):
        detail = response.data.get("detail")

    if response.status_code == 401:
        response.data = {
            "code": "UNAUTHORIZED",
            "message": str(detail or "Требуется авторизация"),
        }

    elif response.status_code == 403:
        response.data = {
            "code": "FORBIDDEN",
            "message": str(detail or "Доступ запрещён"),
        }

    elif response.status_code == 404:
        response.data = {
            "code": "NOT_FOUND",
            "message": str(detail or "Не найдено"),
        }

    return response