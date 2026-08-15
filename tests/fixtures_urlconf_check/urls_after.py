"""ROOT_URLCONF for the unregistered-route audit fixture (ticket #106),
after a developer hand-adds a route to `legacy/urls.py` the pre-apiver way —
`legacy/urls_after.py`'s one extra route, otherwise identical to
`urls_baseline.py`."""

from django.urls import include, path

from tests.fixtures_urlconf_check.api.v1.registry import v1

urlpatterns = [
    path("api/v1/", include(v1.urls)),
    path("", include("tests.fixtures_urlconf_check.legacy.urls_after")),
]
