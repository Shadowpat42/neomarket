import uuid
from django.db import models

from products.models import Product
from shared_models.models import BaseImage, BaseCharacteristic


class ReserveOperation(models.Model):
    """
    Idempotency table for POST /api/v1/inventory/reserve.
    One row per idempotency_key; stores the original success response
    so repeat requests return the same payload without double-deducting.
    """

    idempotency_key = models.UUIDField(primary_key=True)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class FulfilledOrder(models.Model):
    """
    Idempotency table for POST /api/v1/inventory/fulfill.

    ADR – idempotency for fulfill:
      Option A) Separate fulfilled_orders table (chosen).
        + Zero risk of double deduction on retry: first INSERT wins, subsequent
          SELECT finds the row and returns early.
        + Simple to reason about; no coupling to SKU quantities.
        - Extra table and one INSERT per request.
      Option B) last_fulfilled_order field on SKU model.
        - Can't handle multi-SKU orders atomically; race condition if two SKUs
          belong to the same order.
      Option C) Check reserved_quantity before decrement.
        - Cannot distinguish "already fulfilled" from "never had a reserve".
          Double call after partial retry could silently corrupt data.
      Chosen: Option A — lowest risk of double deduction + O(1) idempotency
      check inside the same transaction.
    """

    order_id = models.UUIDField(primary_key=True)
    fulfilled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Выполненный заказ"
        verbose_name_plural = "Выполненные заказы"

    class Meta:
        verbose_name = "Операция резервирования"
        verbose_name_plural = "Операции резервирования"

    def __str__(self):
        return str(self.idempotency_key)


class SKU(models.Model):
    """Конкретный вариант товара: цвет, память, размер и т.п."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="skus")

    name = models.CharField(max_length=255)
    price = models.PositiveIntegerField()
    discount = models.PositiveIntegerField(default=0)
    cost_price = models.PositiveIntegerField(null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    article = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SKU"
        verbose_name_plural = "SKU"

    def __str__(self):
        return f"{self.product.title} — {self.name}"


class SKUImage(BaseImage):
    """Изображение конкретного SKU."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="images")

    class Meta:
        verbose_name = "Изображение SKU"
        verbose_name_plural = "Изображения SKU"


class SKUCharacteristic(BaseCharacteristic):
    """Характеристика конкретного SKU."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, related_name="characteristics")

    class Meta:
        verbose_name = "Характеристика SKU"
        verbose_name_plural = "Характеристики SKU"