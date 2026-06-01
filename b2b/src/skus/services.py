from rest_framework.exceptions import PermissionDenied

from shared_models.models import BaseProductStatus


def resolve_sku_create_side_effects(product, *, is_first_sku: bool, previous_status: str):
    """
    Обновляет статус товара после создания SKU.
    Возвращает тип события для Moderation (CREATED / EDITED) или None.
    """
    if previous_status == BaseProductStatus.HARD_BLOCKED:
        raise PermissionDenied("Cannot add SKU to hard-blocked product")

    if is_first_sku and previous_status == BaseProductStatus.CREATED:
        product.status = BaseProductStatus.ON_MODERATION
        product.save(update_fields=["status", "updated_at"])
        return "CREATED"

    if previous_status in (BaseProductStatus.MODERATED, BaseProductStatus.BLOCKED):
        product.status = BaseProductStatus.ON_MODERATION
        product.save(update_fields=["status", "updated_at"])
        return "EDITED"

    return None
