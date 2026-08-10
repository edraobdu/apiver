from rest_framework import viewsets
from rest_framework.filters import SearchFilter

from addresses.models import Address
from addresses.serializers import AddressReadSerializer, AddressWriteSerializer


class AddressViewSet(viewsets.ModelViewSet):
    queryset = Address.objects.all().order_by("id")
    filter_backends = [SearchFilter]
    search_fields = ["city", "country"]

    def get_serializer_class(self):
        if self.action in ("list", "retrieve"):
            return AddressReadSerializer
        return AddressWriteSerializer
