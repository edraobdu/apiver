"""The aggregation root (ADR 0007 item 2) — also this fixture's
ROOT_URLCONF, for simplicity; a real project's actual root urls.py would
include this once instead."""

from django.urls import include, path

from apiver.drf import Alias
from tests.fixtures_manifest.api.v1.registry import v1
from tests.fixtures_manifest.api.v2.registry import v2

stable = Alias("stable", target=v2)

urlpatterns = [
    path("api/v1/", include(v1.urls)),
    path("api/v2/", include(v2.urls)),
    path("api/stable/", stable.urls),
]
