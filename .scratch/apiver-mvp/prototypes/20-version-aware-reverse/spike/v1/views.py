from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from payments.models import Payment
from spike.v1.serializers import NaivePaymentV1Serializer, PaymentV1Serializer, UserV1Serializer
from users.models import UserProfile


class NaivePaymentV1ViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().order_by("id")
    serializer_class = NaivePaymentV1Serializer


class PaymentV1ViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().order_by("id")
    serializer_class = PaymentV1Serializer

    @action(detail=False, methods=["get"])
    def whoami(self, request):
        """The register-time-stamping proposal, tested directly.

        `stamped_at_register` is set once, on the class, when V1 registers it — exactly
        what "decorate the view from register()" would do. `request.apiver_version` is
        set per request by the mount-time wrapper. Serving this under both versions
        shows which of the two can actually tell them apart.
        """
        return Response(
            {
                "stamped_at_register": getattr(type(self), "stamped_at_register", None),
                "stamped_on_request": getattr(request, "apiver_version", None).name,
            }
        )


class UserV1ViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all().order_by("id")
    serializer_class = UserV1Serializer
