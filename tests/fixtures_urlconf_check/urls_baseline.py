"""ROOT_URLCONF for the unregistered-route audit fixture (ticket #106),
before the hand-added route: the Aggregation Root (`v1`'s own mount) plus
the pre-adoption `legacy/` surface, dual-mounted exactly as adoption leaves
it (ADR 0007)."""

from django.urls import include, path

from tests.fixtures_urlconf_check.api.v1.registry import v1

urlpatterns = [
    path("api/v1/", include(v1.urls)),
    path("", include("tests.fixtures_urlconf_check.legacy.urls_before")),
]
