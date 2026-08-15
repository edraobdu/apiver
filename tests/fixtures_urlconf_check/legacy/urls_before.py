"""The pre-adoption surface (ticket #106 fixture, case (b)): a project's own
per-app `urls.py`, still mounted alongside the new Aggregation Root exactly
as ADR 0007's adoption story describes — deliberately, not a mistake, so
this must never get flagged just for existing."""

from django.urls import path

from tests.testapp.views import healthz

urlpatterns = [
    path("legacy/", healthz, name="legacy-healthz"),
]
