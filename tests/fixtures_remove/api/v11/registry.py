"""One of v10's two direct children — already squashed by hand."""

from tests.fixtures_remove.api.v10.registry import v10
from tests.testapp.views import PaymentViewSetV11

v11 = v10.derive("v11")
v11.override("payments", PaymentViewSetV11, basename="payments")
v11.override("schema/", v11.schema_view(prefix="api/v11/"), name="schema")
v11.override("docs/", v11.docs_view(), name="docs")
