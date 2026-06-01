import json
import uuid
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone


def send_product_event(product, event_type, idempotency_key=None):
    """Отправляет событие CREATED/EDITED в Moderation Service."""
    payload = {
        "idempotency_key": str(idempotency_key or uuid.uuid4()),
        "product_id": str(product.id),
        "seller_id": str(product.seller_id),
        "event": event_type,
        "date": timezone.now().isoformat().replace("+00:00", "Z"),
    }

    url = (
        f"{settings.MODERATION_SERVICE_URL.rstrip('/')}"
        "/api/v1/events/product"
    )
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Service-Key": settings.MODERATION_SERVICE_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=settings.MODERATION_REQUEST_TIMEOUT):
            pass
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Moderation service returned HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Moderation service is unavailable") from exc

    return payload
