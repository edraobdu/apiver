from rest_framework import viewsets

from payments.models import Payment
from spike.plain.serializers import PlainPaymentSerializer, PlainUserSerializer
from users.models import UserProfile


class PlainPaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all().order_by("id")
    serializer_class = PlainPaymentSerializer


class PlainUserViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all().order_by("id")
    serializer_class = PlainUserSerializer
