"""v30's only direct child — already squashed by hand."""

from tests.fixtures_remove.api.v30.registry import v30
from tests.testapp.views import PaymentViewSetV31

v31 = v30.derive("v31")
v31.override("payments", PaymentViewSetV31, basename="payments")
v31.override("schema/", v31.schema_view(prefix="api/v31/"), name="schema")
v31.override("docs/", v31.docs_view(), name="docs")
