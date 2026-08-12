from datetime import timedelta

from django.urls import include, path
from django.utils import timezone

from apiver.drf import Alias, Version

from .views import (
    InvoiceViewSet,
    InvoiceViewSetV2,
    PaymentsSummaryView,
    PaymentViewSet,
    PaymentViewSetV3,
    PingViewSet,
    PlainPingView,
    RedactedInvoiceViewSetV2,
    RefundViewSetV2,
    WidgetViewSet,
    healthz,
    pong,
)

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")
v1.register("payments", PaymentViewSet, basename="payments")
v1.register("payments/summary/", PaymentsSummaryView, name="payments-summary")
v1.register("pong/", pong, name="pong")
v1.register("plain-ping/", PlainPingView, name="plain-ping")
v1.register("invoices", InvoiceViewSet, basename="invoices")
v1.register("widgets", WidgetViewSet, basename="widgets")

# V2 never registers payments/ping/etc itself — it inherits v1's entire
# resolution table live, and only adds what's new to it (ticket 08).
v2 = v1.derive("v2")
v2.register("refunds", RefundViewSetV2, basename="refunds")

# ticket 14: two removal idioms, both schema-correct — Meta.fields surgery
# (override, drops internal_note from the inherited "invoices" resource) and
# del self.fields[...] in __init__ (a fresh registration, since it doesn't
# need to replace anything V1 already serves).
v2.override("invoices", InvoiceViewSetV2, basename="invoices")
v2.register("invoices-redacted", RedactedInvoiceViewSetV2, basename="invoices-redacted")

# V3 exercises the loud verbs (ticket 09): payments gets a new shape, ping
# is gone under V3 while V1/V2 keep serving it unchanged.
v3 = v2.derive("v3")
v3.override("payments", PaymentViewSetV3, basename="payments")
v3.remove("ping")

v1.freeze()

# "stable" is a movable name, re-pointed by editing target= — today it names
# v2. Promoting it to v3 later means changing only this line: its
# schema_view() proxies to whatever its current target already built for
# itself (ticket 12), so nothing below has to change.
stable = Alias("stable", target=v2)

# Ticket 13: deprecation/sunset gating, kept off v1/v2/v3 so it can't
# interact with their own tests. `deprecated_base` is a Version with no
# parent, proving gating isn't special-cased away from the unnamespaced base
# (the ticket's explicit worry about `request.resolver_match`-based
# approaches). `sunset_clock` isolates one fixed sunset instant so a test can
# move the wall clock across it and prove gating reads the live object on
# every request rather than a value computed once. `unmounted` is registered
# but never given a urlpatterns entry, standing in for "version not mounted".
DEPRECATED_BASE_SUNSET = timezone.now() + timedelta(days=365)
deprecated_base = Version("deprecated-base")
deprecated_base.register("ping", PingViewSet, basename="ping")
deprecated_base.deprecate(sunset=DEPRECATED_BASE_SUNSET)

SUNSET_CLOCK_INSTANT = timezone.now() + timedelta(days=1)
sunset_clock = Version("sunset-clock")
sunset_clock.register("ping", PingViewSet, basename="ping")
sunset_clock.deprecate(sunset=SUNSET_CLOCK_INSTANT)

unmounted = Version("unmounted")
unmounted.register("ping", PingViewSet, basename="ping")

urlpatterns = [
    path("api/v1/", include(v1.urls)),
    path("api/v2/", include(v2.urls)),
    path("api/v3/", include(v3.urls)),
    path("api/stable/", stable.urls),
    path("api/v1/schema/", v1.schema_view(prefix="api/v1/"), name="v1-schema"),
    path("api/v2/schema/", v2.schema_view(prefix="api/v2/"), name="v2-schema"),
    path("api/v3/schema/", v3.schema_view(prefix="api/v3/"), name="v3-schema"),
    path("api/stable/schema/", stable.schema_view(), name="stable-schema"),
    path("api/deprecated-base/", include(deprecated_base.urls)),
    path("api/sunset-clock/", include(sunset_clock.urls)),
    # Outside every Version's mount entirely — ADR 0005 item 10's fallback
    # target: a name apiver.drf.reverse must still resolve while a versioned
    # request is being served.
    path("healthz/", healthz, name="healthz"),
]
