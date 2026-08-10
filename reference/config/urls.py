from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from healthz import healthz
from legacy.views import LegacyInvoiceViewSet
from orders.views import OrderViewSet
from payments.views import PaymentsSummaryView, PaymentViewSet
from users.views import UserViewSet

# DefaultRouter, because that's what most projects reach for first — the API-root
# view and format-suffixed patterns it adds are exactly the kind of thing that
# makes adopting a delta-composition router later interesting.
router = DefaultRouter()
router.register("users", UserViewSet, basename="users")
router.register("payments", PaymentViewSet, basename="payments")
router.register("orders", OrderViewSet, basename="orders")
router.register("legacy-invoices", LegacyInvoiceViewSet, basename="legacy-invoices")

urlpatterns = [
    path("api/healthz/", healthz, name="healthz"),
    # explicit view before router.urls: the router's detail-route regex is
    # generic enough to swallow "payments/summary/" as pk="summary" otherwise
    path("api/payments/summary/", PaymentsSummaryView.as_view(), name="payments-summary"),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
