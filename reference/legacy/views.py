from rest_framework import viewsets

from legacy.models import LegacyInvoice
from legacy.serializers import LegacyInvoiceSerializer


class LegacyInvoiceViewSet(viewsets.ModelViewSet):
    """Slated for removal in V2 — `/api/v1/legacy-invoices` must not exist there."""

    queryset = LegacyInvoice.objects.all()
    serializer_class = LegacyInvoiceSerializer
