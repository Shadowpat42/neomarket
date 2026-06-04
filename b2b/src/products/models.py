import uuid
from django.db import models
from shared_models.models import BaseImage, BaseCharacteristic, BaseProductStatus


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.name
    
class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller_id = models.UUIDField(help_text="ID продавца из сервиса авторизации")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')

    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=BaseProductStatus.choices,
        default=BaseProductStatus.CREATED,
        help_text="Статус модерации"
    )
    deleted = models.BooleanField(default=False)
    blocking_reason_id = models.UUIDField(null=True, blank=True)
    moderator_comment = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Продукты'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class Image(BaseImage):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')

    class Meta:
        verbose_name = 'Изображение'
        verbose_name_plural = 'Изображения'

    def __str__(self):
        return f"{self.product.title} - {self.url}"

class Characteristic(BaseCharacteristic):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='characteristics')

    class Meta:
        verbose_name = 'Характеристика'
        verbose_name_plural = 'Характеристики'

    def __str__(self):
        return f"{self.product.title}: {self.name} = {self.value}"


class BlockingReason(models.Model):
    """Справочник причин блокировки (заполняется при событии BLOCKED от Moderation)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Причина блокировки"
        verbose_name_plural = "Причины блокировки"

    def __str__(self):
        return self.title


class ProductFieldReport(models.Model):
    """Замечание модератора по конкретному полю товара или SKU."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="field_reports"
    )
    field_name = models.CharField(max_length=64)
    sku_id = models.UUIDField(null=True, blank=True)
    comment = models.TextField()

    class Meta:
        verbose_name = "Замечание модератора"
        verbose_name_plural = "Замечания модератора"
        ordering = ["field_name"]

    def __str__(self):
        return f"{self.product_id}: {self.field_name}"


class ProcessedModerationEvent(models.Model):
    """
    Idempotency table for POST /api/v1/moderation/events.
    One row per idempotency_key; prevents duplicate processing of the same
    moderation decision even if Moderation retries the delivery.
    """

    idempotency_key = models.UUIDField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Обработанное событие модерации"
        verbose_name_plural = "Обработанные события модерации"

    def __str__(self):
        return str(self.idempotency_key)