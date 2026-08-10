from django.urls import include, path

from apiver.drf import Version

from .views import PingViewSet

v1 = Version("v1")
v1.register("ping", PingViewSet, basename="ping")

urlpatterns = [
    path("api/v1/", include(v1.urls)),
]
