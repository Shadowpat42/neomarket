from django.contrib import admin, messages

from .models import BlockingReason, Ticket, TicketFieldReport


class TicketFieldReportInline(admin.TabularInline):
    model = TicketFieldReport
    extra = 0
    readonly_fields = ("field_path", "message", "severity")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = (
        "id", "product_id", "seller_id", "status", "queue_priority",
        "assigned_moderator", "claimed_at", "created_at",
    )
    list_filter = ("status", "queue_priority", "kind")
    search_fields = ("product_id__iexact", "seller_id__iexact")
    readonly_fields = ("id", "created_at", "updated_at", "claimed_at", "claim_expires_at")
    inlines = [TicketFieldReportInline]


@admin.register(BlockingReason)
class BlockingReasonAdmin(admin.ModelAdmin):
    """
    ADR — catalogue storage (US-MOD-06):
      Option A) Enum in code — requires migration on every change; no runtime CRUD.
      Option B) DB table with Admin CRUD (chosen) — new reasons without deploy;
        historical FK references preserved by soft-delete (is_active=False).
      Option C) i18n catalogue — adds translation infra overhead; unnecessary for MVP.
      Chosen: B — simplest runtime CRUD, safe FK history, easy future i18n addition.
    """

    list_display = ("code", "title", "hard_block", "is_active")
    list_filter = ("hard_block", "is_active")
    search_fields = ("code", "title")
    readonly_fields = ("id",)

    def delete_model(self, request, obj):
        """
        Soft-delete if the reason is referenced by any ticket;
        hard-delete only when no historical references exist.
        """
        if obj.tickets.exists():
            obj.is_active = False
            obj.save(update_fields=["is_active"])
            self.message_user(
                request,
                f"BlockingReason '{obj.code}' is referenced by existing tickets "
                "and was deactivated instead of deleted.",
                level=messages.WARNING,
            )
        else:
            obj.delete()

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.delete_model(request, obj)
