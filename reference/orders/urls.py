from django.urls import path
from rest_framework.routers import SimpleRouter

from orders.views import OrderViewSet, OrdersExportView

# SimpleRouter, not DefaultRouter — orders is the plainest app in the project and
# the odd one out on router choice too, same as addresses/notifications.
router = SimpleRouter()
router.register("orders", OrderViewSet, basename="orders")

urlpatterns = [
    # Same swallow hazard as payments/summary — explicit before router, always.
    path("orders/export/", OrdersExportView.as_view(), name="orders-export"),
] + router.urls
