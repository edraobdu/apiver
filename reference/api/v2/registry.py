"""V2 — hand-authored, unlike api/v1/registry.py (`apiver migrate` only ever
adopts the Base Version). Every change here is one of the change-shape
catalogue's rows; see api/v2/serializers.py and api/v2/views.py for the idiom
each one uses.
"""

from api.v1.registry import v1

from .views import (
    OrderViewSetV2,
    PaymentViewSetV2,
    SpectacularSwaggerViewV2,
    UserViewSetV2,
    WebhookEndpointViewSetV2,
)

v2 = v1.derive("v2")

# Field rename (row 5), field removal (row 6), and the combined nested-restructure
# + SerializerMethodField-output-change resource (rows 9, 10) plus @action removal
# (row 14b) — see api/v2/serializers.py and api/v2/views.py.
v2.override("users", UserViewSetV2, basename="users")
v2.override("orders", OrderViewSetV2, basename="orders")
v2.override("payments", PaymentViewSetV2, basename="payments")

# Whole-resource removal (row 12) — legacy-invoices does not exist in v2 or later.
v2.remove("legacy-invoices")

# URL prefix change (row 13) — no first-class "move" primitive: remove the old
# key, register the same (version-suffixed) handler under the new one. This is a
# schema-visible change, but reported to a diff as delete+add, losing the fact
# that it's the same resource under a shorter path.
v2.remove("integrations/webhooks")
v2.register("webhooks", WebhookEndpointViewSetV2, basename="webhooks")

# The drf-spectacular correctness demo (issue #22): v2 gets its own schema and
# docs routes, scoped to exactly v2's own surface (ADR 0002 Consequences) —
# neither leaks the other version's routes.
v2.override("docs/", SpectacularSwaggerViewV2, name="docs")
v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
