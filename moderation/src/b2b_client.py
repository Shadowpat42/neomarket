"""
Best-effort HTTP client for Moderation → B2B events.

Sends moderation decisions to B2B POST /api/v1/moderation/events.
Errors are intentionally NOT re-raised so callers can decide on rollback strategy.
"""

from __future__ import annotations

import json
import os
import uuid as uuid_lib
from datetime import datetime, timezone as dt_timezone
from typing import Any
from urllib import request as urlrequest
from urllib.error import URLError


def _now_iso() -> str:
    now = datetime.now(tz=dt_timezone.utc)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _b2b_moderation_endpoint() -> str:
    b2b_base_url = os.getenv("B2B_URL", "http://b2b:8001").rstrip("/")
    return f"{b2b_base_url}/api/v1/moderation/events"


def send_moderated_event(
    *,
    product_id: Any,
    idempotency_key: Any | None = None,
    moderator_comment: str | None = None,
) -> None:
    """
    Notify B2B that a product has been approved (MODERATED).
    B2B sets product.status = MODERATED and makes it visible in the catalog.

    Raises URLError / OSError on network failure so the caller can roll back.
    """
    endpoint = _b2b_moderation_endpoint()
    mod_to_b2b_key = os.getenv("MOD_TO_B2B_KEY", "mod_to_b2b_key")

    body = {
        "idempotency_key": str(idempotency_key or uuid_lib.uuid4()),
        "product_id": str(product_id),
        "event_type": "MODERATED",
        "moderator_comment": moderator_comment,
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Service-Key": mod_to_b2b_key,
        },
    )
    with urlrequest.urlopen(req, timeout=3):
        return
