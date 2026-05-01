from django.db import models

# ----------------------------------------------------------------------
# 1. Вспомогательные классы
# ----------------------------------------------------------------------

class BaseProductStatus(models.TextChoices):
    """Статус товара"""
    CREATED = 'CREATED', 'Создан'
    ON_MODERATION = 'ON_MODERATION', 'На модерации'
    MODERATED = 'MODERATED', 'Одобрен'
    BLOCKED = 'BLOCKED', 'Заблокирован'

# ----------------------------------------------------------------------
# 2. Абстрактные модели
# ----------------------------------------------------------------------

class BaseImage(models.Model):
    """Абстрактная модель для изображения (url + порядок)"""
    url = models.URLField('URL изображения')
    ordering = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        abstract = True
        ordering = ['ordering']

    def __str__(self):
        return self.url

class BaseCharacteristic(models.Model):
    """Абстрактная модель для характеристики (имя + значение)"""
    name = models.CharField('Название', max_length=255)
    value = models.CharField('Значение', max_length=255)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name}: {self.value}"