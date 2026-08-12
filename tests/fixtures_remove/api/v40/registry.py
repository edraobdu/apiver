"""A deprecated leaf with no descendants at all — `apiver remove v40`
should simply unmount it, with no child registry.py to rewrite."""

from datetime import UTC, datetime

from apiver.drf import Version
from tests.testapp.views import PaymentViewSet

v40 = Version("v40")
v40.register("payments", PaymentViewSet, basename="payments")
v40.register("schema/", v40.schema_view(prefix="api/v40/"), name="v40-schema")
v40.register("docs/", v40.docs_view(), name="v40-docs")
v40.deprecate(sunset=datetime(2030, 1, 1, tzinfo=UTC))
