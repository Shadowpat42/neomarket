from django.urls import path

from .views import GetNextProductView, TicketApproveView

urlpatterns = [
    # Legacy skeleton endpoint
    path("api/v1/product-moderation/get-next", GetNextProductView.as_view()),

    # US-MOD-03: Approve ticket
    path("api/v1/tickets/<uuid:ticket_id>/approve", TicketApproveView.as_view(), name="ticket-approve"),
]
