from django.http import JsonResponse
from django.views import View
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView


class PingViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"status": "ok"})


class PaymentSerializer(serializers.Serializer):
    id = serializers.CharField()


class PaymentViewSet(viewsets.ViewSet):
    serializer_class = PaymentSerializer

    def list(self, request):
        return Response({"results": ["p1", "p2"]})

    def retrieve(self, request, pk=None):
        return Response({"id": pk})


class RefundViewSetV2(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": ["r1"]})


class PaymentV2Serializer(serializers.Serializer):
    id = serializers.CharField()
    version = serializers.CharField()


class PaymentViewSetV2(viewsets.ViewSet):
    """Overrides PaymentViewSet, one version deep, with a different detail
    shape and no list route — used by the generic override-mechanics tests,
    which register it onto a Version literally named "v2"."""

    serializer_class = PaymentV2Serializer

    def retrieve(self, request, pk=None):
        return Response({"id": pk, "version": "v2"})


class PaymentV3Serializer(serializers.Serializer):
    id = serializers.CharField()
    version = serializers.CharField()


class PaymentViewSetV3(viewsets.ViewSet):
    """Overrides PaymentViewSet with a different detail shape, and no list
    route, so an override collapsing the route count doesn't leak the
    parent's stale paths (ADR 0001 item 3). This is the one actually wired
    into the testapp's V3 in urls.py."""

    serializer_class = PaymentV3Serializer

    def retrieve(self, request, pk=None):
        return Response({"id": pk, "version": "v3"})


class PaymentsSummaryView(APIView):
    def get(self, request):
        return Response({"summary": "ok"})


@api_view(["GET"])
def pong(request):
    return Response({"status": "pong"})


class PlainPingView(View):
    def get(self, request):
        return JsonResponse({"status": "plain"})
