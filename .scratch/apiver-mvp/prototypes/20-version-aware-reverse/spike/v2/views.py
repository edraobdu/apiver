from spike.v1.views import UserV1ViewSet
from spike.v2.serializers import UserV2Serializer


class UserV2ViewSet(UserV1ViewSet):
    serializer_class = UserV2Serializer
