import uuid
from django.db import models


class Order(models.Model):
    STATUS_CHOICES = [
        ("CREATED", "Создан"),
        ("PAID", "Оплачен"),
        ("ASSEMBLING", "В сборке"),
        ("CANCELLED", "Отменён"),
        ("CANCEL_PENDING", "Отмена ожидает повтора"),
        ("RESERVE_FAILED", "Ошибка резерва"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user_id = models.UUIDField()
    idempotency_key = models.CharField(max_length=255, unique=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="PAID")
    total_amount = models.PositiveIntegerField(default=0)

    cancel_reason = models.TextField(blank=True, default="")
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user_id"]),
            models.Index(fields=["idempotency_key"]),
        ]

    def __str__(self):
        return f"Order {self.id} - {self.status}"


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")

    product_id = models.UUIDField()
    sku_id = models.UUIDField()

    product_title = models.CharField(max_length=255)
    sku_name = models.CharField(max_length=255)

    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField()
    line_total = models.PositiveIntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sku_name} x {self.quantity}"