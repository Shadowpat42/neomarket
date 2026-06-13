from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from skus.models import SKU
from shared_models.models import BaseProductStatus

from .models import Invoice, InvoiceItem
from .serializers import InvoiceCreateSerializer, InvoiceResponseSerializer


class InvoiceCreateView(APIView):
    """
    POST /api/v1/invoices
    Creates a new invoice in CREATED status.

    Validation order (per DoD):
      1. Empty items      → 400 INVALID_REQUEST
      2. SKU not found    → 404 NOT_FOUND
      3. Wrong owner      → 403 NOT_OWNER
      4. Not MODERATED    → 400 INVALID_REQUEST
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InvoiceCreateSerializer(data=request.data)
        if not serializer.is_valid():
            # Surface the first meaningful error message
            items_errors = serializer.errors.get("items")
            if items_errors and isinstance(items_errors, list) and not items_errors[0]:
                # empty list passed but validated fine — handled by validate_items
                pass
            return Response(
                {
                    "code": "INVALID_REQUEST",
                    "message": str(
                        next(iter(serializer.errors.get("items", ["Invalid data"])))
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        items_data = serializer.validated_data["items"]

        if not items_data:
            return Response(
                {
                    "code": "INVALID_REQUEST",
                    "message": "At least one item is required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        seller_id = request.user.id

        # Resolve and validate each SKU before touching the DB
        sku_objs: list[tuple[SKU, int]] = []

        for item in items_data:
            sku_id = item["sku_id"]
            quantity = item["quantity"]

            try:
                sku = SKU.objects.select_related("product").get(id=sku_id)
            except SKU.DoesNotExist:
                return Response(
                    {"code": "NOT_FOUND", "message": "SKU not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if str(sku.product.seller_id) != str(seller_id):
                return Response(
                    {
                        "code": "NOT_OWNER",
                        "message": "One or more SKUs do not belong to the authenticated seller",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if sku.product.status != BaseProductStatus.MODERATED:
                return Response(
                    {
                        "code": "INVALID_REQUEST",
                        "message": "Invoice can only be created for MODERATED products",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            sku_objs.append((sku, quantity))

        # All checks passed — create invoice atomically
        invoice = Invoice.objects.create(seller_id=seller_id)
        InvoiceItem.objects.bulk_create(
            [
                InvoiceItem(invoice=invoice, sku=sku, quantity=qty)
                for sku, qty in sku_objs
            ]
        )

        # Re-fetch with prefetch for serialization
        invoice = (
            Invoice.objects.prefetch_related("items__sku").get(id=invoice.id)
        )

        return Response(
            InvoiceResponseSerializer(invoice).data,
            status=status.HTTP_201_CREATED,
        )
