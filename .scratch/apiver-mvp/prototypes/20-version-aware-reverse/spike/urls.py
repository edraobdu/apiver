"""Spike URLconf — activated per-test via @pytest.mark.urls, never the project default.

The Base Version mounts bare (ADR 0001 item 4); authored Versions carry an app_name and
get an instance namespace; the Alias reuses V2's exact patterns under its own instance
namespace.
"""

from django.urls import include, path

from healthz import healthz
from spike.apiver_core import Alias
from spike.v1.registry import v1
from spike.v2.registry import v2

stable = Alias("stable", target=v2)

urlpatterns = [
    # Deliberately outside every Version — the unversioned routes any real project has
    # alongside its API (health checks, admin, auth, webhooks).
    path("healthz/", healthz, name="healthz"),
    path("api/v1/", include(v1.urls)),
    path("api/v2/", include(v2.urls)),
    path("api/stable/", include(stable.urls, namespace=stable.name)),
]
