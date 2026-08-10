from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from webhooks.exceptions import WebhookDeliveryError
from webhooks.models import WebhookEndpoint
from webhooks.serializers import WebhookEndpointSerializer


class WebhookEndpointViewSet(viewsets.ModelViewSet):
    queryset = WebhookEndpoint.objects.all().order_by("id")
    serializer_class = WebhookEndpointSerializer

    @action(detail=True, methods=["post"], url_path="test-delivery")
    def test_delivery(self, request, pk=None):
        webhook = self.get_object()
        if not webhook.is_active:
            raise WebhookDeliveryError(webhook.target_url, reason="endpoint is inactive")
        return Response({"delivered": True, "target_url": webhook.target_url})
