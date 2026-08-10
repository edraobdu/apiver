from spike.v1.views import PaymentViewSet
from spike.v2.serializers import PaymentV2Serializer


class PaymentV2ViewSet(PaymentViewSet):
    serializer_class = PaymentV2Serializer
