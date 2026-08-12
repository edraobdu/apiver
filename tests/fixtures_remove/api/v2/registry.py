"""V2: derives from v1, already squashed by hand — every key v1 resolves
(ping, payments, schema/, docs/) is explicitly override()n here, satisfying
`apiver remove v1`'s precondition. `apiver remove v1` should cut this
version's `.derive('v1')` line and flip every override() into register(),
turning it into its own independent Base Version."""

from tests.fixtures_remove.api.v1.registry import v1
from tests.testapp.views import PaymentViewSetV2, PingViewSet

v2 = v1.derive("v2")
v2.override("ping", PingViewSet, basename="ping")
v2.override("payments", PaymentViewSetV2, basename="payments")
v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
v2.override("docs/", v2.docs_view(), name="docs")
