from rest_framework import serializers

from notifications.models import Notification


# Named "NotifSerializer", not "NotificationSerializer" — every other app in this
# project spells its resource out in full (PaymentSerializer, AddressReadSerializer).
# This one didn't, because somebody was in a hurry once and nobody circled back.
# Left as-is deliberately: apiver's version-suffixed class naming (ADR 0003) still
# has to work against a name nobody would pick if they were starting fresh.
class NotifSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "verb", "read", "created_at"]
