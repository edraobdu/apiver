from spike.apiver_core import Version
from spike.v1.views import OrderViewSet, PaymentsSummaryView, PaymentViewSet, UserViewSet

v1 = Version("v1")
v1.register_viewset("users", UserViewSet)
v1.register_viewset("payments", PaymentViewSet)
v1.register_viewset("orders", OrderViewSet)
v1.register_view(
    "payments-summary", PaymentsSummaryView, url_path="payments/summary/", name="payments-summary"
)
