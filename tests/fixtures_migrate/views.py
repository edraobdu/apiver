"""A small, scattered pre-apiver API — the "before" state `apiver migrate`
(ticket 17) adopts. Mirrors reference/'s shape at a fraction of the size:
one SimpleRouter viewset (no format-suffix duplicates, no api-root), one
DefaultRouter viewset with an extra @action (format-suffix duplicates and
its own api-root view must both be silently skipped), an explicit APIView,
an `@api_view` function, a plain Django View, and a viewset mounted two
segments deep at its own router's root (proves the router-local prefix is
recovered with no extra segment of its own)."""

from django.http import JsonResponse
from django.views import View
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView


class WidgetViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": []})

    def retrieve(self, request, pk=None):
        return Response({"id": pk})


class GadgetViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": []})

    def retrieve(self, request, pk=None):
        return Response({"id": pk})

    @action(detail=True)
    def activate(self, request, pk=None):
        return Response({"activated": True})


class GadgetSummaryView(APIView):
    def get(self, request):
        return Response({"summary": "ok"})


@api_view(["GET"])
def ping(request):
    return Response({"status": "ok"})


class HealthzView(View):
    def get(self, request):
        return JsonResponse({"status": "ok"})


class WebhookViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": []})

    def retrieve(self, request, pk=None):
        return Response({"id": pk})
