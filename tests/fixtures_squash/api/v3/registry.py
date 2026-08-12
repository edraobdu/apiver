"""V3: overrides payments again, removes ping entirely — the squash target.
After `apiver squash v3`: payments comes from v3 itself, refunds is
inherited unchanged from v2, ping is gone, and v1/v2 are never imported
again."""

from tests.fixtures_squash.api.v2.registry import v2
from tests.testapp.views import PaymentViewSetV3

v3 = v2.derive("v3")
v3.override("payments", PaymentViewSetV3, basename="payments")
v3.remove("ping")
v3.override("schema/", v3.schema_view(prefix="api/v3/"), name="schema")
v3.override("docs/", v3.docs_view(), name="docs")
