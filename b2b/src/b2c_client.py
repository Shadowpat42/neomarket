"""
Best-effort HTTP client for B2B → B2C events.

Events sent here must NOT block the caller if B2C is unavailable.
All calls wrap urlopen in try/except; callers are responsible for logging.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import request as urlrequest


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


def notify_sku_out_of_stock(*, sku_id: Any, product_id: Any) -> None:
    """
    Notify B2C that a SKU's active_quantity has reached 0.
    B2C uses this to hide the SKU from the vitrine until stock is replenished.
    """
    b2c_base_url = os.getenv("B2C_URL", "http://b2c:8002").rstrip("/")
    endpoint = f"{b2c_base_url}/api/v1/events/sku-out-of-stock"

    _post(
        endpoint,
        {
            "event": "SKU_OUT_OF_STOCK",
            "sku_id": str(sku_id),
            "product_id": str(product_id),
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
    B2C uses this to hide the product and all its SKUs from the vitrine.
    """
    import uuid as _uuid

    b2c_base_url = os.getenv("B2C_URL", "http://b2c:8002").rstrip("/")
    endpoint = f"{b2c_base_url}/api/v1/events/product"

    _post(
        endpoint,
        {
            "idempotency_key": idempotency_key or str(_uuid.uuid4()),
            "event": "PRODUCT_BLOCKED",
            "product_id": str(product_id),
            "sku_ids": sku_ids,
        },
    )


def notify_product_deleted(
    *,
    product_id: Any,
    sku_ids: list[str],
    idempotency_key: str | None = None,
) -> None:
    """
    Notify B2C that a product has been deleted (soft delete).
    B2C uses this to hide the product and remove it from carts/wishlists.
    """
    import uuid as _uuid

    b2c_base_url = os.getenv("B2C_URL", "http://b2c:8002").rstrip("/")
    endpoint = f"{b2c_base_url}/api/v1/events/product"

    _post(
        endpoint,
        {
            "idempotency_key": idempotency_key or str(_uuid.uuid4()),
            "event": "PRODUCT_DELETED",
            "product_id": str(product_id),
            "sku_ids": sku_ids,
        },
    )
