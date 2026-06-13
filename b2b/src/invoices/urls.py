from django.urls import path

from .views import InvoiceCreateView

urlpatterns = [
    path("api/v1/invoices", InvoiceCreateView.as_view(), name="invoice-create"),
]
