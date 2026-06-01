import uuid

from django.db import models

from products.models import Product
from shared_models.models import BaseImage, BaseCharacteristic


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
    article = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SKU"
        verbose_name_plural = "SKU"

    def __str__(self):
        return f"{self.product.title} — {self.name}"

    @property
    def active_quantity(self) -> int:
        return max(0, self.stock_quantity - self.reserved_quantity)


class SKUImage(BaseImage):
    """Изображение конкретного SKU."""

    url = models.CharField("URL изображения", max_length=2048)
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
