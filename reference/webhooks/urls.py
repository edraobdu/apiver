from rest_framework.routers import DefaultRouter

from webhooks.views import WebhookEndpointViewSet

# Registered at this file's own root ("") rather than under a "webhooks" prefix —
# config/urls.py mounts this whole file two segments deep, at
# "api/integrations/webhooks/", the deepest nesting in the project and a
# plausible future rename target (catalogue row 13: URL prefix changes).
router = DefaultRouter()
router.register("", WebhookEndpointViewSet, basename="webhooks")

urlpatterns = router.urls
