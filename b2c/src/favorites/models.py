import uuid

from django.db import models


class Favorite(models.Model):
    """
    Избранное покупателя.
    B2C хранит только product_id + user_id; актуальные данные подтягиваются
    batch-запросом к B2B при просмотре списка.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    product_id = models.UUIDField()
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user_id", "product_id")]
        ordering = ["-added_at"]

    def __str__(self):
        return f"Favorite(user={self.user_id}, product={self.product_id})"


VALID_NOTIFY_ON = {"BACK_IN_STOCK", "PRICE_DROP"}


class ProductSubscription(models.Model):
    """
    Подписка на уведомления о товаре.
    MVP: данные сохраняются, фактическая отправка уведомлений вне scope.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    product_id = models.UUIDField()
    notify_on = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user_id", "product_id")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Subscription(user={self.user_id}, product={self.product_id})"
