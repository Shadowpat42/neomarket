from __future__ import annotations

import json
import os
import uuid as uuid_lib
from datetime import datetime
from typing import Any
from urllib import request as urlrequest

from django.utils import timezone


def _isoformat_millis_z(dt: datetime) -> str:
    """
    Example: 2026-03-15T14:30:00.000Z
    """

    dt = dt.astimezone(timezone.utc)
    # Python keeps microseconds; truncate to millis.
    s = dt.isoformat(timespec="milliseconds")
    return s.replace("+00:00", "Z")


def send_product_moderation_event(
    *,
    event: str,
    product_id: Any,
    seller_id: Any,
    idempotency_key: uuid_lib.UUID,
    occurred_at: datetime | None = None,
) -> None:
    """
    Best-effort synchronous POST to Moderation.
    In real deployment this should likely use outbox pattern.
    """

    moderation_base_url = os.getenv("MODERATION_URL", "http://moderation:8003").rstrip("/")
    b2b_to_mod_key = os.getenv("B2B_TO_MOD_KEY", "b2b_to_mod_key")
    endpoint = f"{moderation_base_url}/api/v1/events/product"

    occurred_at = occurred_at or timezone.now()

    payload = {
        "idempotency_key": str(idempotency_key),
        "product_id": str(product_id),
        "seller_id": str(seller_id),
        "event": event,
        "date": _isoformat_millis_z(occurred_at),
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Service-Key": b2b_to_mod_key,
        },
    )
    with urlrequest.urlopen(req, timeout=3) as _resp:
        # We don't parse response body here.
        return

