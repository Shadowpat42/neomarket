from __future__ import annotations

import json
import os
import uuid as uuid_lib
from datetime import datetime
from typing import Any
from urllib import request as urlrequest

from django.utils import timezone


def _isoformat_millis_z(dt: datetime) -> str:
    """Returns ISO 8601 with milliseconds and trailing Z: 2026-03-15T14:30:00.000Z"""
    dt = dt.astimezone(timezone.utc)
    s = dt.isoformat(timespec="milliseconds")
    return s.replace("+00:00", "Z")


def send_product_moderation_event(
    *,
    event_type: str,
    product_id: Any,
    seller_id: Any,
    idempotency_key: uuid_lib.UUID,
    occurred_at: datetime | None = None,
    json_before: dict | None = None,
    json_after: dict | None = None,
) -> None:
    """
    Best-effort synchronous POST to Moderation Service.

    Sends to POST /api/v1/b2b/events with IncomingB2BEvent schema:
        {event_type, idempotency_key, occurred_at,
         payload: {product_id, seller_id, json_before, json_after}}

    json_before — product snapshot BEFORE the edit (required for PRODUCT_EDITED).
    json_after  — product snapshot AFTER the edit (optional, for context).

    In production this should use the outbox pattern for guaranteed delivery.
    """
    moderation_base_url = os.getenv("MODERATION_URL", "http://moderation:8003").rstrip("/")
    b2b_to_mod_key = os.getenv("B2B_TO_MOD_KEY", "b2b_to_mod_key")
    endpoint = f"{moderation_base_url}/api/v1/b2b/events"

    occurred_at = occurred_at or timezone.now()

    body = {
        "event_type": event_type,
        "idempotency_key": str(idempotency_key),
        "occurred_at": _isoformat_millis_z(occurred_at),
        "payload": {
            "product_id": str(product_id),
            "seller_id": str(seller_id),
            "json_before": json_before or {},
            "json_after": json_after or {},
        },
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
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
        return
