from django.urls import path

from .views import (
    B2BEventView,
    BlockingReasonsView,
    GetNextProductView,
    TicketApproveView,
    TicketBlockView,
)

urlpatterns = [
    # US-MOD-02: Get next ticket from queue
    path(
        "api/v1/product-moderation/get-next",
        GetNextProductView.as_view(),
        name="get-next",
    ),

    # US-MOD-06: Blocking reasons catalogue
    path(
        "api/v1/product-blocking-reasons",
        BlockingReasonsView.as_view(),
        name="blocking-reasons",
    ),

    # Incoming events from B2B (X-Service-Key auth)
    path("api/v1/b2b/events", B2BEventView.as_view(), name="b2b-events"),

    # US-MOD-03: Approve ticket
    path(
        "api/v1/tickets/<uuid:ticket_id>/approve",
        TicketApproveView.as_view(),
        name="ticket-approve",
    ),

    # US-MOD-04/05: Block ticket (soft or hard, determined by blocking_reason.hard_block)
    path(
        "api/v1/tickets/<uuid:ticket_id>/block",
        TicketBlockView.as_view(),
        name="ticket-block",
    ),
]
