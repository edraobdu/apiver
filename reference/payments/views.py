from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import Payment
from payments.serializers import PaymentSerializer


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]  # silent behavioral default — no schema delta if changed

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        payment = self.get_object()
        payment.status = "failed"
        payment.save(update_fields=["status"])
        return Response(PaymentSerializer(payment).data)


class PaymentsSummaryView(APIView):
    """Non-viewset route — proves APIViews are first-class citizens, not routers-only."""

    def get(self, request):
        amounts = list(Payment.objects.values_list("amount", flat=True))
        return Response({"total": sum(amounts), "count": len(amounts)})
