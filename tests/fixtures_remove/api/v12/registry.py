"""The other of v10's two direct children — already squashed by hand."""

from tests.fixtures_remove.api.v10.registry import v10
from tests.testapp.views import PaymentViewSetV12

v12 = v10.derive("v12")
v12.override("payments", PaymentViewSetV12, basename="payments")
v12.override("schema/", v12.schema_view(prefix="api/v12/"), name="schema")
v12.override("docs/", v12.docs_view(), name="docs")
