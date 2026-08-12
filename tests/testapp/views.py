from django.http import JsonResponse
from django.views import View
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Invoice


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


class Widget:
    """A plain object, not a model — `HyperlinkedRelatedField.get_url` only
    needs `.pk` (ADR 0005 items 5-8), so nothing heavier is required to
    exercise it."""

    def __init__(self, pk):
        self.pk = pk


class WidgetSerializer(serializers.Serializer):
    """Registered once, on v1, and never touched again by v2 or v3 (ADR
    0005's demonstration: inheritance composes behaviour, not just routes).
    `url` is a plain `HyperlinkedIdentityField` — no apiver import, no
    subclass — proving the zero-effort promise of the `get_url` patch."""

    pk = serializers.CharField()
    url = serializers.HyperlinkedIdentityField(view_name="widgets-detail")


class WidgetViewSet(viewsets.ViewSet):
    serializer_class = WidgetSerializer

    def retrieve(self, request, pk=None):
        data = WidgetSerializer(Widget(pk=pk), context={"request": request}).data
        return Response(data)


def healthz(request):
    """A bare, unversioned route living outside every Version's mount — the
    admin/login/health-check shape ADR 0005 item 10's reverse() fallback
    exists for."""
    return JsonResponse({"status": "ok"})


@api_view(["GET"])
def pong(request):
    return Response({"status": "pong"})


class PlainPingView(View):
    def get(self, request):
        return JsonResponse({"status": "plain"})


def _invoice(pk):
    return Invoice(number=pk, amount="10.00", internal_note="do not expose to clients")


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ["number", "amount", "internal_note"]


class InvoiceViewSet(viewsets.ViewSet):
    """V1: internal_note is (mistakenly) part of the public shape. Also
    carries a custom @action, used to prove `action = None` cleanly removes
    an inherited action — ticket 14's explicit asymmetry with `field =
    None`, which does not."""

    serializer_class = InvoiceSerializer

    def retrieve(self, request, pk=None):
        return Response(InvoiceSerializer(_invoice(pk)).data)

    @action(detail=True)
    def flag(self, request, pk=None):
        return Response({"flagged": True})


class InvoiceV2Serializer(InvoiceSerializer):
    """The canonical field-removal idiom: Meta.fields surgery against the
    parent's list. Confirmed schema-correct — drf-spectacular instantiates
    this class directly, so a field absent from Meta.fields never appears in
    either the response or the schema."""

    class Meta(InvoiceSerializer.Meta):
        fields = [name for name in InvoiceSerializer.Meta.fields if name != "internal_note"]


class InvoiceViewSetV2(InvoiceViewSet):
    serializer_class = InvoiceV2Serializer
    # ticket 14: unadorned and correct — get_extra_actions() drops `flag`
    # from the router with no crash and no silent survival, unlike the
    # field = None footgun below.
    flag = None

    def retrieve(self, request, pk=None):
        return Response(InvoiceV2Serializer(_invoice(pk)).data)


class RedactedInvoiceV2Serializer(InvoiceSerializer):
    """The documented fallback for a dynamically-computed exclusion:
    del self.fields[...] in __init__. Also schema-visible, because
    drf-spectacular instantiates the serializer to read live .fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["internal_note"]


class RedactedInvoiceViewSetV2(viewsets.ViewSet):
    serializer_class = RedactedInvoiceV2Serializer

    def retrieve(self, request, pk=None):
        return Response(RedactedInvoiceV2Serializer(_invoice(pk)).data)


class BrokenInvoiceV2Serializer(InvoiceSerializer):
    """The footgun (ticket 14): DRF silently ignores this. Meta.fields is
    inherited unchanged from InvoiceSerializer.Meta and still names
    internal_note, so ModelSerializer rebuilds it fresh from the model
    instead of dropping it. Never registered on a Version — only used to
    prove apiver raises before this ever reaches production."""

    internal_note = None


class BrokenInvoiceViewSetV2(viewsets.ViewSet):
    """Wires BrokenInvoiceV2Serializer to a handler apiver can register().
    Deliberately never mounted in urls.py — register()/override() on this
    class must raise before it ever reaches a urlconf."""

    serializer_class = BrokenInvoiceV2Serializer

    def retrieve(self, request, pk=None):
        return Response(BrokenInvoiceV2Serializer(_invoice(pk)).data)
