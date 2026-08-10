"""Identical to spike.urls, except `stable` has been promoted from v2 to v3.

Nothing else changes — least of all any caller's reverse() argument.
"""

from django.urls import include, path

from healthz import healthz
from spike.apiver_core import Alias
from spike.v1.registry import v1
from spike.v2.registry import v2
from spike.v3.registry import v3

stable = Alias("stable", target=v3)

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("api/v1/", include(v1.urls)),
    path("api/v2/", include(v2.urls)),
    path("api/v3/", include(v3.urls)),
    path("api/stable/", include(stable.urls, namespace=stable.name)),
]
