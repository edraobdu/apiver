from rest_framework import serializers

from users.models import UserProfile


class UserV2Serializer(serializers.ModelSerializer):
    """A genuine Delta, so V2 isn't a pure passthrough — `email` is gone."""

    class Meta:
        model = UserProfile
        fields = ["id", "username"]
