import uuid
from django.db import models


class CartItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user_id = models.UUIDField(null=True, blank=True)
    session_id = models.CharField(max_length=255, null=True, blank=True)

    product_id = models.UUIDField()
    sku_id = models.UUIDField()
    quantity = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user_id", "sku_id"]),
            models.Index(fields=["session_id", "sku_id"]),
        ]

    def __str__(self):
        return f"{self.sku_id} x {self.quantity}"