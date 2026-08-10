"""V1 serializers. Both are inherited by V2 *unchanged* — that is the whole point."""

from rest_framework import serializers
from rest_framework.reverse import reverse as drf_reverse

from payments.models import Payment
from spike.apiver_core import VersionedHyperlinkedIdentityField


class NaivePaymentV1Serializer(serializers.ModelSerializer):
    """What a developer writes today, with no version-awareness anywhere.

    Both of these resolve through bare URL names, so when this serializer is inherited
    into V2 they keep pointing at V1 — the bug ticket #20 exists to settle.
    """

    url = serializers.HyperlinkedIdentityField(view_name="naive-payments-detail")
    receipt_link = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ["id", "amount", "currency", "url", "receipt_link"]

    def get_receipt_link(self, obj):
        return drf_reverse(
            "naive-payments-detail",
            kwargs={"pk": obj.pk},
            request=self.context.get("request"),
        )


class PaymentV1Serializer(serializers.ModelSerializer):
    """The same serializer, written against the version-aware primitives."""

    url = VersionedHyperlinkedIdentityField(view_name="payments-detail")
    receipt_link = serializers.SerializerMethodField()
    served_by = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ["id", "amount", "currency", "url", "receipt_link", "served_by"]

    def get_receipt_link(self, obj):
        from spike.apiver_core import apiver_reverse

        return apiver_reverse(
            "payments-detail", kwargs={"pk": obj.pk}, request=self.context.get("request")
        )

    def get_served_by(self, obj):
        """The broader ask: can arbitrary serializer logic know which Version it's in?"""
        request = self.context.get("request")
        version = getattr(request, "apiver_version", None)
        return version.name if version is not None else None


class UserV1Serializer(serializers.ModelSerializer):
    class Meta:
        from users.models import UserProfile

        model = UserProfile
        fields = ["id", "username", "email"]
