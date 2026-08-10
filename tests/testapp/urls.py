from django.urls import include, path

from apiver.drf import Version

from .views import (
    PaymentsSummaryView,
    PaymentViewSet,
    PaymentViewSetV2,
    PingViewSet,
    PlainPingView,
    RefundViewSet,
    pong,
)

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")
v1.register("payments", PaymentViewSet, basename="payments")
v1.register("payments/summary/", PaymentsSummaryView, name="payments-summary")
v1.register("pong/", pong, name="pong")
v1.register("plain-ping/", PlainPingView, name="plain-ping")

# V2 never registers payments/ping/etc itself — it inherits v1's entire
# resolution table live, and only adds what's new to it (ticket 08).
v2 = v1.derive("v2")
v2.register("refunds", RefundViewSet, basename="refunds")

# V3 exercises the loud verbs (ticket 09): payments gets a new shape, ping
# is gone under V3 while V1/V2 keep serving it unchanged.
v3 = v2.derive("v3")
v3.override("payments", PaymentViewSetV2, basename="payments")
v3.remove("ping")

v1.freeze()

urlpatterns = [
    path("api/v1/", include(v1.urls)),
    path("api/v2/", include(v2.urls)),
    path("api/v3/", include(v3.urls)),
]
