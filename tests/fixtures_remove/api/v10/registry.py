"""v10: base version, deprecated, branched into two direct children (v11,
v12 below) — `apiver remove v10` should turn both into independent Base
Versions (ADR 0009's pre-amendment draft already tolerates more than one
Base Version)."""

from datetime import UTC, datetime

from apiver.drf import Version
from tests.testapp.views import PaymentViewSet

v10 = Version("v10")
v10.register("payments", PaymentViewSet, basename="payments")
v10.register("schema/", v10.schema_view(prefix="api/v10/"), name="v10-schema")
v10.register("docs/", v10.docs_view(), name="v10-docs")
v10.deprecate(sunset=datetime(2030, 1, 1, tzinfo=UTC))
