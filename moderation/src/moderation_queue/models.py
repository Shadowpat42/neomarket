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

    @classmethod
    def terminal_statuses(cls):
        """Statuses that no longer accept any modifications."""
        return {cls.HARD_BLOCKED}


class BlockingReason(models.Model):
    """
    Catalogue of reasons a product can be blocked.

    hard_block=True → product goes to HARD_BLOCKED (terminal).
    hard_block=False → product goes to BLOCKED (seller can appeal/re-submit).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    hard_block = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} (hard={self.hard_block})"


class Ticket(models.Model):
    """
    Moderation ticket: one ticket per product review request.

    Lifecycle: PENDING → IN_REVIEW → APPROVED | BLOCKED | HARD_BLOCKED
    HARD_BLOCKED is terminal — only a super-admin can undo via Django Admin (data-fix).
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
    blocking_reason = models.ForeignKey(
        BlockingReason,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tickets",
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

    def is_terminal(self) -> bool:
        return self.status in TicketStatus.terminal_statuses()


class IncomingEventLog(models.Model):
    """
    Idempotency log for incoming B2B events.

    Keyed on idempotency_key supplied by the caller (B2B).
    A second request with the same key is acknowledged immediately (202)
    without re-processing, preventing duplicate ticket creation/updates.
    """

    idempotency_key = models.UUIDField(primary_key=True)
    event_type = models.CharField(max_length=50)
    product_id = models.UUIDField(db_index=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["product_id", "processed_at"])]


class TicketFieldReport(models.Model):
    """
    Inline annotation for a specific field that was found invalid.
    Cleared and re-created on each moderation decision.
    """

    SEVERITY_CHOICES = [("INFO", "Info"), ("WARNING", "Warning"), ("ERROR", "Error")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="field_reports",
    )
    field_path = models.CharField(max_length=255)
    message = models.CharField(max_length=1000)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="ERROR")
