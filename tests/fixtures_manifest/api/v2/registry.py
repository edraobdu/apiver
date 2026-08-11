"""V2: overrides payments, deprecated with a fixed sunset.

A fixed instant rather than `timezone.now()`-derived (ticket 16) — two
manifest generations of the same process must agree on their own committed
content, so `apiver manifest` followed immediately by `apiver manifest
--check` is deterministic across separate subprocesses.
"""

from datetime import UTC, datetime

from tests.fixtures_manifest.api.v1.registry import v1
from tests.testapp.views import PaymentViewSetV2

FIXED_SUNSET = datetime(2030, 1, 1, tzinfo=UTC)

v2 = v1.derive("v2")
v2.override("payments", PaymentViewSetV2, basename="payments")
v2.deprecate(sunset=FIXED_SUNSET)
