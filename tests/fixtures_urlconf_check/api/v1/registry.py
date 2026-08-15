"""The single Live Version for the unregistered-route audit fixture
(ticket #106) — just enough to have a real mount for `_owned_urlconf_paths`
to walk."""

from apiver.drf import Version
from tests.testapp.views import PingViewSet

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")
