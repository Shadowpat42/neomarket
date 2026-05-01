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
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=BaseProductStatus.choices,
        default=BaseProductStatus.CREATED,
        help_text="Статус модерации"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Продукт'
        verbose_name_plural = 'Продукты'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class Image(BaseImage):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')

    class Meta:
        verbose_name = 'Изображение'
        verbose_name_plural = 'Изображения'

    def __str__(self):
        return f"{self.product.title} - {self.url}"

class Characteristic(BaseCharacteristic):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='characteristics')

    class Meta:
        verbose_name = 'Характеристика'
        verbose_name_plural = 'Характеристики'

    def __str__(self):
        return f"{self.product.title}: {self.name} = {self.value}"