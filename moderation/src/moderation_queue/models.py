import uuid

from django.contrib.auth.models import User
from django.db import models


class TicketKind(models.TextChoices):
    CREATE = "CREATE"
    EDIT = "EDIT"


class TicketStatus(models.TextChoices):
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


class Ticket(models.Model):
    """
    Moderation ticket: one ticket per product review request.

    Lifecycle: PENDING → IN_REVIEW → APPROVED | BLOCKED | HARD_BLOCKED
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_id = models.UUIDField(db_index=True)
    seller_id = models.UUIDField()
    category_id = models.UUIDField(null=True, blank=True)
    kind = models.CharField(max_length=10, choices=TicketKind.choices)
    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.PENDING,
        db_index=True,
    )
    queue_priority = models.PositiveSmallIntegerField(
        default=3,
        help_text="1 — highest priority, 4 — lowest",
    )
    assigned_moderator = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_tickets",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    claim_expires_at = models.DateTimeField(null=True, blank=True)
    decision_at = models.DateTimeField(null=True, blank=True)
    decision_comment = models.TextField(null=True, blank=True)
    json_before = models.JSONField(null=True, blank=True)
    json_after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["queue_priority", "created_at"]
