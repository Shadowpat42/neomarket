from rest_framework import serializers

from .models import BlockingReason, Ticket


class TicketResponseSerializer(serializers.ModelSerializer):
    assigned_moderator_id = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id",
            "product_id",
            "seller_id",
            "category_id",
            "kind",
            "status",
            "queue_priority",
            "assigned_moderator_id",
            "claimed_at",
            "claim_expires_at",
            "decision_at",
            "created_at",
            "updated_at",
        ]

    def get_assigned_moderator_id(self, obj: Ticket):
        if obj.assigned_moderator_id is None:
            return None
        return obj.assigned_moderator_id


class GetNextTicketSerializer(serializers.ModelSerializer):
    """Response schema for POST /api/v1/queue/claim (TicketResponse + snapshots)."""

    blocking_history = serializers.SerializerMethodField()
    assigned_moderator_id = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            "id",
            "product_id",
            "seller_id",
            "category_id",
            "kind",
            "status",
            "queue_priority",
            "assigned_moderator_id",
            "claimed_at",
            "claim_expires_at",
            "json_before",
            "json_after",
            "blocking_history",
            "created_at",
            "updated_at",
        ]

    def get_assigned_moderator_id(self, obj: Ticket):
        if obj.assigned_moderator_id is None:
            return None
        return obj.assigned_moderator_id

    def get_blocking_history(self, obj: Ticket):
        """
        Present only if the ticket was previously blocked (queue 2).
        Null for new products (queue 1).
        """
        if obj.blocking_reason_id is None:
            return None
        return {
            "blocking_reason": {
                "id": str(obj.blocking_reason.id),
                "title": obj.blocking_reason.title,
            },
            "moderator_comment": obj.decision_comment,
            "field_reports": [
                {
                    "field_name": fr.field_path,
                    "sku_id": None,
                    "comment": fr.message,
                }
                for fr in obj.field_reports.all()
            ],
            "date_blocked": (
                obj.decision_at.isoformat() if obj.decision_at else None
            ),
        }


class BlockingReasonSerializer(serializers.ModelSerializer):
    """Response schema for GET /api/v1/blocking-reasons."""

    class Meta:
        model = BlockingReason
        fields = ["id", "code", "title", "hard_block", "is_active"]
