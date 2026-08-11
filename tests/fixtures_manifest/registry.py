"""A small, fully static Version/Alias graph for the manifest tests
(ticket 16).

Deliberately not `tests.testapp.urls`: that fixture computes its deprecation
sunsets from `timezone.now()` at import time, which would make two manifest
generations of the same process disagree on their own committed content —
exactly the false "stale" this module exists to avoid. Everything here is a
fixed instant instead, so `apiver manifest` followed immediately by
`apiver manifest --check` is deterministic across separate subprocesses.
"""

from datetime import UTC, datetime

from django.urls import include, path

from apiver.drf import Alias, Version
from tests.testapp.views import PaymentViewSet, PaymentViewSetV2, PingViewSet

FIXED_SUNSET = datetime(2030, 1, 1, tzinfo=UTC)

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")
v1.register("payments", PaymentViewSet, basename="payments")
v1.freeze()

v2 = v1.derive("v2")
v2.override("payments", PaymentViewSetV2, basename="payments")
v2.deprecate(sunset=FIXED_SUNSET)

stable = Alias("stable", target=v2)

urlpatterns = [
    path("api/v1/", include(v1.urls)),
    path("api/v2/", include(v2.urls)),
    path("api/stable/", stable.urls),
]
