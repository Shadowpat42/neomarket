"""
Best-effort HTTP client for B2B → B2C events.

All events conform to the B2BEvent schema from B2C OpenAPI:
    {event_type, idempotency_key, occurred_at, payload}

Errors are intentionally NOT re-raised so that a B2C outage never blocks B2B.
Callers should log exceptions before swallowing them if observability is needed.
"""

from __future__ import annotations

import json
import os
import uuid as uuid_lib
from datetime import datetime, timezone as dt_timezone
from typing import Any
from urllib import request as urlrequest


def _now_iso() -> str:
    """Returns current UTC time in ISO 8601 with milliseconds: 2026-03-15T14:30:00.000Z"""
    now = datetime.now(tz=dt_timezone.utc)
    s = now.isoformat(timespec="milliseconds")
    return s.replace("+00:00", "Z")


def _post(endpoint: str, payload: dict) -> None:
    b2b_to_b2c_key = os.getenv("B2B_TO_B2C_KEY", "b2b_to_b2c_key")
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Service-Key": b2b_to_b2c_key,
        },
    )
    with urlrequest.urlopen(req, timeout=3):
        return


def _b2c_events_endpoint() -> str:
    b2c_base_url = os.getenv("B2C_URL", "http://b2c:8002").rstrip("/")
    return f"{b2c_base_url}/api/v1/events/b2b"


def notify_sku_out_of_stock(*, sku_id: Any, product_id: Any) -> None:
    """
    Notify B2C that a SKU's active_quantity has reached 0.
    B2C hides the SKU from the vitrine until stock is replenished.
    """
    _post(
        _b2c_events_endpoint(),
        {
            "event_type": "SKU_OUT_OF_STOCK",
            "idempotency_key": str(uuid_lib.uuid4()),
            "occurred_at": _now_iso(),
            "payload": {
                "sku_id": str(sku_id),
                "product_id": str(product_id),
            },
        },
    )


def notify_product_blocked(
    *,
    product_id: Any,
    sku_ids: list[str],
    idempotency_key: str | None = None,
) -> None:
    """
    Notify B2C that a product has been blocked (soft or hard).
    B2C hides the product and all its SKUs from the vitrine.
    """
    _post(
        _b2c_events_endpoint(),
        {
            "event_type": "PRODUCT_BLOCKED",
            "idempotency_key": idempotency_key or str(uuid_lib.uuid4()),
            "occurred_at": _now_iso(),
            "payload": {
                "product_id": str(product_id),
                "sku_ids": sku_ids,
            },
        },
    )


def notify_product_deleted(
    *,
    product_id: Any,
    sku_ids: list[str],
    idempotency_key: str | None = None,
) -> None:
    """
    Notify B2C that a product has been soft-deleted.
    B2C removes it from the vitrine, carts, and wishlists.
    """
    _post(
        _b2c_events_endpoint(),
        {
            "event_type": "PRODUCT_DELETED",
            "idempotency_key": idempotency_key or str(uuid_lib.uuid4()),
            "occurred_at": _now_iso(),
            "payload": {
                "product_id": str(product_id),
                "sku_ids": sku_ids,
            },
        },
    )
