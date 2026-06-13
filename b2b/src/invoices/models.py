import uuid

from django.db import models

from skus.models import SKU


class InvoiceStatus(models.TextChoices):
    CREATED = "CREATED", "Создана"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED", "Принята частично"
    ACCEPTED = "ACCEPTED", "Принята полностью"
    CANCELLED = "CANCELLED", "Отменена"


class Invoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller_id = models.UUIDField(db_index=True)
    status = models.CharField(
        max_length=32,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.CREATED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invoice {self.id} [{self.status}]"


class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT, related_name="invoice_items")
    quantity = models.PositiveIntegerField()
    accepted_quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = [("invoice", "sku")]

    def __str__(self):
        return f"InvoiceItem {self.sku_id} ×{self.quantity}"
