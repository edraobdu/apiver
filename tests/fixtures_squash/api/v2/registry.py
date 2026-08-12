"""V2: overrides payments, adds refunds fresh — a registration `apiver
squash v3` should absorb as an inherited-unchanged register(), never
touched again by v3."""

from tests.fixtures_squash.api.v1.registry import v1
from tests.testapp.views import PaymentViewSetV2, RefundViewSetV2

v2 = v1.derive("v2")
v2.override("payments", PaymentViewSetV2, basename="payments")
v2.register("refunds", RefundViewSetV2, basename="refunds")
v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
v2.override("docs/", v2.docs_view(), name="docs")
