from spike.plain.views import PlainPaymentViewSet
from spike.v3.serializers import PlainPaymentV3Serializer


class PlainPaymentV3ViewSet(PlainPaymentViewSet):
    serializer_class = PlainPaymentV3Serializer
