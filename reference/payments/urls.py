from django.urls import path
from rest_framework.routers import DefaultRouter

from payments.views import PaymentsSummaryView, PaymentViewSet

router = DefaultRouter()
router.register("payments", PaymentViewSet, basename="payments")

urlpatterns = [
    # explicit view before router.urls: the router's detail-route regex is
    # generic enough to swallow "payments/summary/" as pk="summary" otherwise
    path("payments/summary/", PaymentsSummaryView.as_view(), name="payments-summary"),
] + router.urls
