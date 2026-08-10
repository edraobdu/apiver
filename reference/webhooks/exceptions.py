from rest_framework.exceptions import APIException


class WebhookDeliveryError(APIException):
    """A response shape that isn't DRF's standard `{"detail": ...}` — passing a dict
    as `detail` replaces the body wholesale instead of nesting under it. Catalogue
    row 19 (error shape/status code changes) needs a concrete example to point at;
    this is it. Completely invisible to a schema diff either way."""

    status_code = 422
    default_code = "delivery_failed"

    def __init__(self, target_url, reason):
        super().__init__(detail={"error": "delivery_failed", "target_url": target_url, "reason": reason})
