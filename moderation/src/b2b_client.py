"""
Best-effort HTTP client for Moderation → B2B events.

Sends moderation decisions to B2B POST /api/v1/moderation/events.
Errors are NOT silently swallowed here — callers decide on rollback strategy.
"""

from __future__ import annotations

import json
import os
import uuid as uuid_lib
from datetime import datetime, timezone as dt_timezone
from typing import TYPE_CHECKING, Any
from urllib import request as urlrequest

if TYPE_CHECKING:
    from moderation_queue.models import BlockingReason


def _now_iso() -> str:
    now = datetime.now(tz=dt_timezone.utc)
    return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _b2b_moderation_endpoint() -> str:
    b2b_base_url = os.getenv("B2B_URL", "http://b2b:8001").rstrip("/")
    return f"{b2b_base_url}/api/v1/moderation/events"


def _post(body: dict) -> None:
    endpoint = _b2b_moderation_endpoint()
    mod_to_b2b_key = os.getenv("MOD_TO_B2B_KEY", "mod_to_b2b_key")
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
    _post(
        {
            "idempotency_key": str(idempotency_key or uuid_lib.uuid4()),
            "product_id": str(product_id),
            "event_type": "MODERATED",
            "occurred_at": _now_iso(),
            "moderator_comment": moderator_comment,
        }
    )


def send_blocked_event(
    *,
    product_id: Any,
    idempotency_key: Any | None = None,
    hard_block: bool,
    blocking_reason: "BlockingReason | None" = None,
    comment: str | None = None,
    field_reports: list[dict] | None = None,
) -> None:
    """
    Notify B2B that a product has been blocked (soft or hard).

    hard_block=True  → B2B sets product.status = HARD_BLOCKED (terminal).
    hard_block=False → B2B sets product.status = BLOCKED (seller can resubmit).

    Raises URLError / OSError on network failure so the caller can roll back.
    """
    # Convert internal field_reports format {field_path, message} →
    # B2B contract format {field_name, comment} (b2b/openapi.yaml FieldReport schema).
    b2b_field_reports = [
        {
            "field_name": fr.get("field_path") or fr.get("field_name", ""),
            "comment": fr.get("message") or fr.get("comment", ""),
            **({"sku_id": fr["sku_id"]} if fr.get("sku_id") else {}),
        }
        for fr in (field_reports or [])
    ]

    _post(
        {
            "idempotency_key": str(idempotency_key or uuid_lib.uuid4()),
            "product_id": str(product_id),
            "event_type": "BLOCKED",
            "occurred_at": _now_iso(),
            "hard_block": hard_block,
            "blocking_reason_id": str(blocking_reason.id) if blocking_reason else None,
            "moderator_comment": comment,
            "field_reports": b2b_field_reports,
        }
    )
