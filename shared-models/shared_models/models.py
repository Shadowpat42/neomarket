from django.db import models

class BaseImage(models.Model):
    """Абстрактная модель для изображения."""
    url = models.URLField('URL изображения')
    ordering = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        abstract = True
        ordering = ['ordering']

    def __str__(self):
        return self.url

class BaseCharacteristic(models.Model):
    """Абстрактная модель для характеристики (например, цвет, бренд)."""
    name = models.CharField('Название', max_length=255)
    value = models.CharField('Значение', max_length=255)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name}: {self.value}"