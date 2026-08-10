from spike.v2.registry import v2
from spike.v3.views import PlainPaymentV3ViewSet

v3 = v2.derive("v3")
v3.register_viewset("plain-payments", PlainPaymentV3ViewSet, basename="payment")
