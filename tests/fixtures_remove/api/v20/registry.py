"""v20: base version, deprecated — v21 (below) has *not* been squashed, so
`apiver remove v20` must refuse."""

from datetime import UTC, datetime

from apiver.drf import Version
from tests.testapp.views import PaymentViewSet

v20 = Version("v20")
v20.register("payments", PaymentViewSet, basename="payments")
v20.register("schema/", v20.schema_view(prefix="api/v20/"), name="v20-schema")
v20.register("docs/", v20.docs_view(), name="v20-docs")
v20.deprecate(sunset=datetime(2030, 1, 1, tzinfo=UTC))
