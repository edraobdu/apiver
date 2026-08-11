"""A small, dedicated urlconf (ticket 22) proving `docs_view()` resolves to the
right schema for both a Base Version (no Django instance namespace) and a
derived Version (namespaced) — the two cases `schema_route_name` treats
differently. Kept separate from `testapp/urls.py`'s own `v1`/`v2`/`v3`, which
mount `schema_view()` as a sibling `path()` entry outside `include(v1.urls)`
rather than through `register()`, and so never exercises the namespace
question this file is for.
"""

from django.urls import include, path

from apiver.drf import Version

from .views import PingViewSet

v1 = Version("docs-v1")
v1.register("ping", PingViewSet, basename="ping")
v1.register("schema/", v1.schema_view(prefix="api/docs-v1/"), name=v1.schema_route_name)
v1.register("docs/", v1.docs_view(), name=f"{v1.name}-docs")

v2 = v1.derive("docs-v2")
v2.override("schema/", v2.schema_view(prefix="api/docs-v2/"), name=v2.schema_route_name)
v2.override("docs/", v2.docs_view(), name="docs")

urlpatterns = [
    path("api/docs-v1/", include(v1.urls)),
    path("api/docs-v2/", include(v2.urls)),
]
