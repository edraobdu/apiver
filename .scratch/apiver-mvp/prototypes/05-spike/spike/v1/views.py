from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from spike.models import Order, Payment, UserProfile
from spike.v1.serializers import OrderV1Serializer, PaymentV1Serializer, UserV1Serializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserV1Serializer


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentV1Serializer


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderV1Serializer


class PaymentsSummaryView(APIView):
    """Non-viewset route — proves APIViews are first-class per ADR 0001."""

    def get(self, request):
        amounts = list(Payment.objects.values_list("amount", flat=True))
        return Response({"total": sum(amounts), "count": len(amounts)})
