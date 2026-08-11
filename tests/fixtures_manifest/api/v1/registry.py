"""V1: frozen, the parent every manifest test's V2 derives from."""

from apiver.drf import Version
from tests.testapp.views import PaymentViewSet, PingViewSet

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")
v1.register("payments", PaymentViewSet, basename="payments")
v1.freeze()
