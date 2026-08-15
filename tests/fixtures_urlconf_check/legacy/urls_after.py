"""The same pre-adoption surface as `urls_before.py`, plus one route
hand-added the old way *after* apiver was adopted (ticket #106 fixture,
case (a)) — exactly the silent bypass `check_unregistered_urlconf_routes`
exists to catch."""

from django.urls import path

from tests.testapp.views import healthz, pong

urlpatterns = [
    path("legacy/", healthz, name="legacy-healthz"),
    path("legacy/new-route/", pong, name="legacy-new-route"),
]
