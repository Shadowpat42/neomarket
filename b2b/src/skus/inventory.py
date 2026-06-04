"""
Reserve / Unreserve service layer (US-B2B-08).

Invariant (maintained at all times):
    stock_quantity == reserved_quantity + active_quantity
    (active_quantity is computed, not stored)

"Reserve" increments reserved_quantity by N → active_quantity decreases by N.
"Unreserve" decrements reserved_quantity by N → active_quantity increases by N.

All mutations run inside a SELECT FOR UPDATE transaction (all-or-nothing).
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import SKU, ReserveOperation


class InsufficientStockError(Exception):
    def __init__(self, failed_items: list[dict]) -> None:
        self.failed_items = failed_items
        super().__init__("Insufficient stock for one or more SKUs")


def send_sku_out_of_stock_event(*, sku_id: Any, product_id: Any) -> None:
    """
    Best-effort notification to B2C when active_quantity reaches 0.
    Delegates to b2c_client; errors are intentionally not re-raised
    so that reserve success is never blocked by B2C availability.
    """
    from b2c_client import notify_sku_out_of_stock

    notify_sku_out_of_stock(sku_id=sku_id, product_id=product_id)


def reserve_skus(
    idempotency_key: uuid.UUID,
    order_id: uuid.UUID,
    items: list[dict],
) -> tuple[dict, bool]:
    """
    All-or-nothing reserve of the given SKU quantities.

    Returns (result_dict, is_idempotent_repeat).
    Raises InsufficientStockError when any SKU lacks enough active_quantity.

    Algorithm:
    1. Check idempotency cache → return cached result if present.
    2. BEGIN; SELECT … FOR UPDATE ORDER BY id (canonical lock order → no deadlocks).
    3. Validate all SKUs in one pass; fail fast if any check fails (no writes yet).
    4. Update reserved_quantity for each SKU.
    5. Persist idempotency record.
    6. COMMIT.
    7. Outside transaction: best-effort SKU_OUT_OF_STOCK events.
    """
    # --- idempotency check (outside transaction, cheap read) ---
    try:
        cached = ReserveOperation.objects.get(idempotency_key=idempotency_key)
        return cached.result, True
    except ReserveOperation.DoesNotExist:
        pass

    sku_ids = [item["sku_id"] for item in items]
    quantity_map: dict[str, int] = {
        str(item["sku_id"]): int(item["quantity"]) for item in items
    }

    out_of_stock_skus: list[SKU] = []

    with transaction.atomic():
        # Lock rows in consistent order to prevent deadlocks under concurrent requests.
        locked_skus = list(
            SKU.objects.select_for_update()
            .filter(id__in=sku_ids)
            .order_by("id")
        )

        if len(locked_skus) != len(sku_ids):
            found = {str(s.id) for s in locked_skus}
            missing = [sid for sid in sku_ids if str(sid) not in found]
            raise ValueError(f"SKUs not found: {missing}")

        # --- validation pass (no writes) ---
        failed_items: list[dict] = []
        for sku in locked_skus:
            qty = quantity_map[str(sku.id)]
            active = sku.stock_quantity - sku.reserved_quantity
            if active < qty:
                reason = "OUT_OF_STOCK" if active == 0 else "INSUFFICIENT_STOCK"
                failed_items.append(
                    {
                        "sku_id": str(sku.id),
                        "requested": qty,
                        "available": active,
                        "reason": reason,
                    }
                )

        if failed_items:
            raise InsufficientStockError(failed_items)

        # --- update pass ---
        result_items: list[dict] = []
        for sku in locked_skus:
            qty = quantity_map[str(sku.id)]
            sku.reserved_quantity += qty
            sku.save()
            remaining = sku.stock_quantity - sku.reserved_quantity
            result_items.append(
                {
                    "sku_id": str(sku.id),
                    "reserved_quantity": qty,
                    "remaining_stock": remaining,
                }
            )
            if remaining == 0:
                out_of_stock_skus.append(sku)

        reserved_at = timezone.now().isoformat()
        result: dict = {
            "reserved": True,
            "order_id": str(order_id),
            "reserved_at": reserved_at,
            "items": result_items,
        }
        ReserveOperation.objects.create(
            idempotency_key=idempotency_key,
            result=result,
        )

    # --- best-effort events (outside transaction) ---
    for sku in out_of_stock_skus:
        try:
            send_sku_out_of_stock_event(sku_id=sku.id, product_id=sku.product_id)
        except Exception:
            pass

    return result, False


def unreserve_skus(order_id: uuid.UUID, items: list[dict]) -> dict:
    """
    Compensating transaction: move N units from reserved back to active.

    Defensive: clamps reserved_quantity to 0 to prevent negative values
    (e.g. double-unreserve of the same order).
    """
    sku_ids = [item["sku_id"] for item in items]
    quantity_map: dict[str, int] = {
        str(item["sku_id"]): int(item["quantity"]) for item in items
    }

    with transaction.atomic():
        locked_skus = list(
            SKU.objects.select_for_update()
            .filter(id__in=sku_ids)
            .order_by("id")
        )

        for sku in locked_skus:
            qty = quantity_map[str(sku.id)]
            sku.reserved_quantity = max(0, sku.reserved_quantity - qty)
            sku.save()

    return {
        "order_id": str(order_id),
        "status": "UNRESERVED",
        "processed_at": timezone.now().isoformat(),
    }
