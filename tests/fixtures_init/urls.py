from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter, SimpleRouter

from . import views

widgets_router = SimpleRouter()
widgets_router.register("widgets", views.WidgetViewSet, basename="widgets")

gadgets_router = DefaultRouter()
gadgets_router.register("gadgets", views.GadgetViewSet, basename="gadgets")

webhooks_router = DefaultRouter()
# Registered at this router's own root ("") — mirrors reference/webhooks:
# this whole file is mounted two segments deep below, at
# "api/integrations/webhooks/", so the router contributes no extra segment
# of its own.
webhooks_router.register("", views.WebhookViewSet, basename="webhooks")

urlpatterns = [
    path("api/healthz/", views.HealthzView.as_view(), name="healthz"),
    path("api/ping/", views.ping, name="ping"),
    path("api/gadgets/summary/", views.GadgetSummaryView.as_view(), name="gadgets-summary"),
    path("api/", include(widgets_router.urls)),
    path("api/", include(gadgets_router.urls)),
    path("api/integrations/webhooks/", include(webhooks_router.urls)),
    # A pre-existing, unscoped drf-spectacular schema/docs pair (ticket #40,
    # ticket 22) — proves init special-cases both SpectacularAPIView (into
    # a `schema_view(prefix=...)` call instead of registering it raw) and
    # SpectacularSwaggerView (into a version-qualified name and `url_name=`,
    # instead of preserving the bare "schema"/"docs" names verbatim).
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # Outside --prefix "api/" — proves the prefix filter excludes it.
    path("status/", views.HealthzView.as_view(), name="status"),
    # A second, unrelated ancestor with no shared prefix with "api/" short of
    # ""  — proves --prefix is repeatable and unions non-overlapping trees
    # (ticket #61).
    path("legacy/archive/", views.HealthzView.as_view(), name="legacy-archive"),
]
