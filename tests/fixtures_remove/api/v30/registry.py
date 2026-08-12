"""v30: base version, never deprecated — `apiver remove v30` must refuse
without --force, even though v31 (below) is already squashed."""

from apiver.drf import Version
from tests.testapp.views import PaymentViewSet

v30 = Version("v30")
v30.register("payments", PaymentViewSet, basename="payments")
v30.register("schema/", v30.schema_view(prefix="api/v30/"), name="v30-schema")
v30.register("docs/", v30.docs_view(), name="v30-docs")
