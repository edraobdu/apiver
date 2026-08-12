"""V1: base version — ping, payments, schema/docs. The tail of the chain
`apiver squash v3` should absorb."""

from apiver.drf import Version
from tests.testapp.views import PaymentViewSet, PingViewSet

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")
v1.register("payments", PaymentViewSet, basename="payments")
v1.register("schema/", v1.schema_view(prefix="api/v1/"), name="v1-schema")
v1.register("docs/", v1.docs_view(), name="v1-docs")
