from django.urls import include, path

from apiver.drf import Version

from .views import PaymentsSummaryView, PaymentViewSet, PingViewSet, PlainPingView, pong

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")
v1.register("payments", PaymentViewSet, basename="payments")
v1.register("payments/summary/", PaymentsSummaryView, name="payments-summary")
v1.register("pong/", pong, name="pong")
v1.register("plain-ping/", PlainPingView, name="plain-ping")

urlpatterns = [
    path("api/v1/", include(v1.urls)),
]
