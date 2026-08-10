from rest_framework import serializers

from webhooks.models import WebhookEndpoint


class WebhookEndpointSerializer(serializers.ModelSerializer):
    # Written once at creation, never read back — the concrete seed for catalogue
    # row 22 (read-only/writable toggle): this field is the mirror image of an
    # ordinary read-only field like `id`, and a future version loosening it to
    # readable (or vice versa, tightening a writable field to read-only) is exactly
    # the shape that row describes.
    secret = serializers.CharField(write_only=True)

    class Meta:
        model = WebhookEndpoint
        fields = ["id", "target_url", "event_type", "secret", "is_active"]

    def validate_target_url(self, value):
        # Custom validate_* logic — declarative field constraints (URLField's own
        # scheme/format checking) already reject garbage; this rejects a URL that's
        # syntactically fine but violates a business rule (http, not https). Trivial
        # to write, invisible to a schema diff (catalogue row 7).
        if not value.startswith("https://"):
            raise serializers.ValidationError("target_url must use https.")
        return value
