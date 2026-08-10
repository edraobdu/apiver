from rest_framework import serializers

from addresses.models import Address
from addresses.validators import validate_postal_code_for_country
from users.serializers import UserSerializer


class AddressReadSerializer(serializers.ModelSerializer):
    """Nests the owning user — the read/write split exists because a nested
    representation and a writable FK can't both be `user` on one serializer
    without fighting DRF's own field resolution. A version boundary later has
    to pick one of these two classes to override, not "the" address serializer."""

    user = UserSerializer(read_only=True)

    class Meta:
        model = Address
        fields = ["id", "user", "line1", "line2", "city", "postal_code", "country", "is_primary"]


class AddressWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["id", "user", "line1", "line2", "city", "postal_code", "country", "is_primary"]

    def validate(self, attrs):
        postal_code = attrs.get("postal_code", getattr(self.instance, "postal_code", None))
        country = attrs.get("country", getattr(self.instance, "country", None))
        validate_postal_code_for_country(postal_code, country)
        return attrs
