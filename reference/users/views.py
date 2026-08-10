from rest_framework import viewsets

from users.models import UserProfile
from users.serializers import UserSerializer


class UserViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.all()
    serializer_class = UserSerializer
