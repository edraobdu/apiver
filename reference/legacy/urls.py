from rest_framework.routers import DefaultRouter

from legacy.views import LegacyInvoiceViewSet

router = DefaultRouter()
router.register("legacy-invoices", LegacyInvoiceViewSet, basename="legacy-invoices")

urlpatterns = router.urls
