from spike.apiver_core import Version
from spike.plain.views import PlainPaymentViewSet, PlainUserViewSet
from spike.v1.views import NaivePaymentV1ViewSet, PaymentV1ViewSet, UserV1ViewSet

v1 = Version("v1")
v1.register_viewset("payments", PaymentV1ViewSet, basename="payments")
v1.register_viewset("naive-payments", NaivePaymentV1ViewSet, basename="naive-payments")
v1.register_viewset("users", UserV1ViewSet, basename="users")

# Registered only here, in V1, and inherited by V2 untouched. The basenames match what
# HyperlinkedModelSerializer derives from the model name, so the plain serializers need
# no view_name configuration at all.
v1.register_viewset("plain-payments", PlainPaymentViewSet, basename="payment")
v1.register_viewset("plain-users", PlainUserViewSet, basename="userprofile")
