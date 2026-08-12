import pytest
from rest_framework import viewsets
from rest_framework.response import Response

from apiver.drf import Version


class PaymentViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": []})


class PaymentViewSetV2(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": []})


class RefundViewSet(viewsets.ViewSet):
    def list(self, request):
        return Response({"results": []})


def test_register_on_a_derived_version_raises_when_class_name_lacks_the_suffix():
    v1 = Version("v1")
    v2 = v1.derive("v2")

    with pytest.raises(ValueError):
        v2.register("payments", PaymentViewSet, basename="payments")


def test_register_on_a_derived_version_succeeds_when_class_name_carries_the_suffix():
    v1 = Version("v1")
    v2 = v1.derive("v2")

    v2.register("payments", PaymentViewSetV2, basename="payments")

    assert "^payments/$" in v2.resolution_table


def test_override_on_a_derived_version_raises_when_class_name_lacks_the_suffix():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v2 = v1.derive("v2")

    with pytest.raises(ValueError):
        v2.override("payments", RefundViewSet, basename="payments")


def test_override_reaffirming_the_same_handler_is_exempt_from_the_suffix_check():
    """apiver squash (ADR 0009) needs to re-declare an inherited-unchanged
    registration as an explicit override() on a later version — the handler
    doesn't carry that version's own suffix because nothing about it
    actually changed. Exempt only when it's the exact same object already
    resolving at this key (the case above, a genuinely different
    non-suffixed handler, still raises)."""
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v2 = v1.derive("v2")

    v2.override("payments", PaymentViewSet, basename="payments")

    assert v2.resolution_table["^payments/$"].registration.handler is PaymentViewSet


def test_override_on_a_derived_version_succeeds_when_class_name_carries_the_suffix():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v2 = v1.derive("v2")

    v2.override("payments", PaymentViewSetV2, basename="payments")

    assert v2.resolution_table["^payments/$"].registration.handler is PaymentViewSetV2


def test_base_version_is_exempt_from_the_suffix_check():
    v1 = Version("v1")

    v1.register("payments", PaymentViewSet, basename="payments")

    assert "^payments/$" in v1.resolution_table


def test_function_based_view_is_exempt_from_the_suffix_check():
    v1 = Version("v1")
    v2 = v1.derive("v2")

    v2.register("pong/", lambda request: None, name="pong")

    assert any(route.registration.key == "pong/" for route in v2.resolution_table.values())


def test_a_deeper_derivation_requires_its_own_suffix_not_an_ancestors():
    v1 = Version("v1")
    v2 = v1.derive("v2")
    v3 = v2.derive("v3")

    with pytest.raises(ValueError):
        v3.override("payments", PaymentViewSetV2, basename="payments")
