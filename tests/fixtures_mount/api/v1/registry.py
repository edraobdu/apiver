from apiver.drf import Version
from tests.testapp.views import PingViewSet

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")
v1.freeze()
