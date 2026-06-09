from rest_framework import serializers

from .models import Ticket


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
