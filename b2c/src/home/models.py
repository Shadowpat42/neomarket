import uuid

from django.db import models


# ── US-CART-04: Banners ───────────────────────────────────────────────────────

class Banner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    image_url = models.CharField(max_length=500)
    link = models.CharField(max_length=500)
    priority = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority"]

    def __str__(self):
        return self.title


class BannerEvent(models.Model):
    EVENT_CHOICES = [("impression", "Показ"), ("click", "Клик")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    banner = models.ForeignKey(Banner, on_delete=models.CASCADE, related_name="events")
    user_id = models.UUIDField(null=True, blank=True)
    event = models.CharField(max_length=20, choices=EVENT_CHOICES)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event} on {self.banner_id}"


# ── US-CART-05: Collections ───────────────────────────────────────────────────

class Collection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    cover_image_url = models.CharField(max_length=500, blank=True, default="")
    target_url = models.CharField(max_length=500, blank=True, default="")
    priority = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority"]

    def __str__(self):
        return self.title


class CollectionProduct(models.Model):
    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name="products"
    )
    product_id = models.UUIDField()
    ordering = models.IntegerField(default=0)

    class Meta:
        unique_together = [("collection", "product_id")]
        ordering = ["ordering"]

    def __str__(self):
        return f"{self.collection_id} → {self.product_id}"
