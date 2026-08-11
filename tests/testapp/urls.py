from django.urls import include, path

from apiver.drf import Alias, Version

from .views import (
    PaymentsSummaryView,
    PaymentViewSet,
    PaymentViewSetV3,
    PingViewSet,
    PlainPingView,
    RefundViewSetV2,
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
v2.register("refunds", RefundViewSetV2, basename="refunds")

# V3 exercises the loud verbs (ticket 09): payments gets a new shape, ping
# is gone under V3 while V1/V2 keep serving it unchanged.
v3 = v2.derive("v3")
v3.override("payments", PaymentViewSetV3, basename="payments")
v3.remove("ping")

v1.freeze()

# "stable" is a movable name, re-pointed by editing target= — today it names
# v2. Its schema route reuses v2's own already-built SpectacularAPIView
# instance (v2_schema below), never a second call to v2.schema_view()
# (ticket 12).
stable = Alias("stable", target=v2)
v2_schema = v2.schema_view(prefix="api/v2/")

urlpatterns = [
    path("api/v1/", include(v1.urls)),
    path("api/v2/", include(v2.urls)),
    path("api/v3/", include(v3.urls)),
    path("api/stable/", stable.urls),
    path("api/v1/schema/", v1.schema_view(prefix="api/v1/"), name="v1-schema"),
    path("api/v2/schema/", v2_schema, name="v2-schema"),
    path("api/v3/schema/", v3.schema_view(prefix="api/v3/"), name="v3-schema"),
    path("api/stable/schema/", v2_schema, name="stable-schema"),
]
