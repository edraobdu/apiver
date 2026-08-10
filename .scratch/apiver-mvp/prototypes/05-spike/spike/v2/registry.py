from spike.apiver_core import Version
from spike.v1.registry import v1
from spike.v2.views import PaymentV2ViewSet

# The whole point of the spike: two statements. `users` and `payments-summary`
# are inherited from v1 for free — nothing declared here for them.
v2 = Version("v2", parent=v1)
v2.register_viewset("payments", PaymentV2ViewSet)
v2.remove("orders")
