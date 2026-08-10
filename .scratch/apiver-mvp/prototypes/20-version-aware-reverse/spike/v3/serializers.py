from rest_framework import serializers

from payments.models import Payment


class PlainPaymentV3Serializer(serializers.HyperlinkedModelSerializer):
    """Visibly different from V1/V2, so a re-pointed alias is observable in the body."""

    class Meta:
        model = Payment
        fields = ["id", "url", "amount", "currency", "status"]
