from rest_framework import serializers

from payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    # computed at serialization time — changing this method's logic later produces
    # no schema delta at all, a diff-blind change by construction
    display_amount = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "amount",
            "currency",
            "status",
            "card_last4",
            "card_brand",
            "display_amount",
            "created_at",
        ]

    def get_display_amount(self, obj):
        return f"{obj.amount / 100:.2f} {obj.currency}"
