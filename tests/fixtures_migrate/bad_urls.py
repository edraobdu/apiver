from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import bad_views

gizmos_router = SimpleRouter()
gizmos_router.register("gizmos", bad_views.GizmoViewSet, basename="gizmos")

urlpatterns = [
    # F1: a factory/closure-built class has no importable symbol.
    path("api/", include(gizmos_router.urls)),
    # F5: a lambda has no importable symbol either.
    path("api/lambda-view/", lambda request: None, name="lambda-view"),
]
