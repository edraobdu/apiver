from rest_framework.routers import SimpleRouter

from addresses.views import AddressViewSet

# SimpleRouter here, DefaultRouter next door in payments/ — deliberately
# inconsistent, the way router choice actually drifts across a codebase that
# grew one app at a time rather than from one shared scaffold.
router = SimpleRouter()
router.register("addresses", AddressViewSet, basename="addresses")

urlpatterns = router.urls
