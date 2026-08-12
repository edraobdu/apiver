"""V2: overrides payments with a viewset that adds a field and drops the
list route — gives `diff`/`check` fixture tests both a field-level change
and a resource-level (path removal) change to see in the same version."""

from tests.fixtures_diff.api.v1.registry import v1
from tests.testapp.views import PaymentViewSetV2

v2 = v1.derive("v2")
v2.override("payments", PaymentViewSetV2, basename="payments")
