from django.urls import include, path

from spike.v1.registry import v1
from spike.v2.registry import v2

urlpatterns = [
    path("api/v1/", include(v1.urlpatterns())),
    path("api/v2/", include((v2.urlpatterns(), "v2"), namespace="v2")),
]
