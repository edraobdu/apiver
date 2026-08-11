from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from orders.serializers import OrderSerializer
from payments.serializers import PaymentSerializer
from users.serializers import UserSerializer


class CardSchema(serializers.Serializer):
    """Not registered anywhere — exists only so `@extend_schema_field` below can
    give `card` a proper nested-object schema instead of drf-spectacular's opaque
    string fallback for a SerializerMethodField it can't infer a return type for."""

    last4 = serializers.CharField()
    brand = serializers.CharField()


class UserSerializerV2(UserSerializer):
    """V2 renames `full_name` to `display_name` (catalogue row 5). There is no
    dedicated rename primitive — this is the field-add + field-remove idiom, which
    is exactly what a schema diff between v1 and v2 will report it as: one field
    deleted, one added, even though it's the same underlying attribute."""

    display_name = serializers.CharField(source="full_name")

    class Meta(UserSerializer.Meta):
        fields = ["id", "username", "email", "display_name", "is_active"]


class OrderSerializerV2(OrderSerializer):
    """V2 drops `status` entirely (catalogue row 6) — Meta.fields surgery against
    the parent's list, the ADR 0006-canonical removal idiom. `status = None` would
    raise (ADR 0006 item 1): that idiom is refused, not just discouraged."""

    class Meta(OrderSerializer.Meta):
        fields = [name for name in OrderSerializer.Meta.fields if name != "status"]


class PaymentSerializerV2(PaymentSerializer):
    """Two independent V2 changes land on the same resource, same as a real
    version would:

    - `card_last4`/`card_brand` collapse into a nested `card` object (catalogue
      row 9, flat<->nested restructuring). There's no first-class "nest these
      fields" primitive: the flat fields drop out of Meta.fields, a new
      SerializerMethodField assembles the nested read shape, and `create`/`update`
      translate the nested write shape back to the two flat model fields by hand.
    - `get_display_amount`'s output format changes (catalogue row 10) — still a
      SerializerMethodField, so this produces *no* schema delta at all; the only
      way to catch it is to actually call the endpoint and read the body.
    """

    card = serializers.SerializerMethodField()

    class Meta(PaymentSerializer.Meta):
        fields = ["id", "amount", "currency", "status", "card", "display_amount", "created_at"]

    @extend_schema_field(CardSchema)
    def get_card(self, obj):
        return {"last4": obj.card_last4, "brand": obj.card_brand}

    def get_display_amount(self, obj):
        return f"${obj.amount / 100:.2f}"

    def _card_fields(self):
        card = self.initial_data.get("card") or {}
        return {"card_last4": card.get("last4", ""), "card_brand": card.get("brand", "")}

    def create(self, validated_data):
        validated_data.update(self._card_fields())
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "card" in self.initial_data:
            validated_data.update(self._card_fields())
        return super().update(instance, validated_data)
