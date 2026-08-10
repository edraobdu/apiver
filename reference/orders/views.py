from rest_framework import viewsets

from orders.models import Order
from orders.serializers import OrderSerializer


class OrderViewSet(viewsets.ModelViewSet):
    """Plain resource, no frills — a candidate for whole-resource removal in V2."""

    queryset = Order.objects.all()
    serializer_class = OrderSerializer
