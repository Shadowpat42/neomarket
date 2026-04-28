from django.db import models
from shared_models.models import BaseImage, BaseCharacteristic

class Product(models.Model):
    STATUS_CHOICES = [
        ('CREATED', 'Создан'),
        ('ON_MODERATION', 'На модерации'),
        ('MODERATED', 'Одобрен'),
        ('BLOCKED', 'Заблокирован'),
    ]
    title = models.CharField(max_length=255)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CREATED')
    category_id = models.IntegerField()
    category_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class Image(BaseImage):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')

class Characteristic(BaseCharacteristic):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='characteristics')