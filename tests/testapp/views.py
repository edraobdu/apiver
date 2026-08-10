from django.http import JsonResponse
from django.views import View
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView


class PingViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"status": "ok"})


class PaymentViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": ["p1", "p2"]})

    def retrieve(self, request, pk=None):
        return Response({"id": pk})


class RefundViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": ["r1"]})


class PaymentViewSetV2(viewsets.ViewSet):
    """Overrides PaymentViewSet with a different detail shape, and no list
    route, so an override collapsing the route count doesn't leak the
    parent's stale paths (ADR 0001 item 3)."""

    def retrieve(self, request, pk=None):
        return Response({"id": pk, "version": "v2"})


class PaymentsSummaryView(APIView):
    def get(self, request):
        return Response({"summary": "ok"})


@api_view(["GET"])
def pong(request):
    return Response({"status": "pong"})


class PlainPingView(View):
    def get(self, request):
        return JsonResponse({"status": "plain"})
