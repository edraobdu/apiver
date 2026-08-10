from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import Order
from orders.renderers import OrdersCSVRenderer
from orders.serializers import OrderSerializer


class OrderViewSet(viewsets.ModelViewSet):
    """Plain resource, no frills — a candidate for whole-resource removal in V2."""

    queryset = Order.objects.all()
    serializer_class = OrderSerializer


class OrdersExportView(APIView):
    """Non-viewset route with a non-JSON renderer — proves both "APIViews are
    first-class" (map.md standing decision) and "renderer changes are clean but
    diff-blind" (catalogue row 21) at once."""

    renderer_classes = [OrdersCSVRenderer]

    def get(self, request):
        orders = Order.objects.values("id", "reference", "status").order_by("id")
        return Response(list(orders))
