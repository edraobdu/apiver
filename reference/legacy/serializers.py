from rest_framework import serializers

from legacy.models import LegacyInvoice


class LegacyInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegacyInvoice
        fields = ["id", "number", "amount"]
