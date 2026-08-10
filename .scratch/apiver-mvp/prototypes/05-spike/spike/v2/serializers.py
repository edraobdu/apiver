from rest_framework import serializers

from spike.v1.serializers import PaymentV1Serializer


class PaymentV2Serializer(PaymentV1Serializer):
    """Change a field's type (row 3 of the change-shape catalogue): int -> decimal."""

    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
