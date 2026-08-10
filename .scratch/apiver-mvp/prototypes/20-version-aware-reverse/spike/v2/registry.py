from spike.v1.registry import v1
from spike.v2.views import UserV2ViewSet

# V2's entire Delta: one override. `payments` and `naive-payments` are inherited and
# are never mentioned here — which is exactly the case ticket #20 is about.
v2 = v1.derive("v2")
v2.register_viewset("users", UserV2ViewSet, basename="users")
