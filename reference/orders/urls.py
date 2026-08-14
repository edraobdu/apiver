from django.urls import path
from rest_framework.routers import SimpleRouter

from orders.views import OrderItemViewSet, OrderViewSet, OrdersExportView

# SimpleRouter, not DefaultRouter — orders is the plainest app in the project and
# the odd one out on router choice too, same as addresses/notifications.
router = SimpleRouter()
router.register("orders", OrderViewSet, basename="orders")
# Nested-router spike: no NestedSimpleRouter, no extra library — the parent
# lookup group lives directly in the prefix string SimpleRouter is handed.
router.register(r"orders/(?P<order_pk>[^/.]+)/items", OrderItemViewSet, basename="order-items")

urlpatterns = [
    # Same swallow hazard as payments/summary — explicit before router, always.
    path("orders/export/", OrdersExportView.as_view(), name="orders-export"),
] + router.urls
