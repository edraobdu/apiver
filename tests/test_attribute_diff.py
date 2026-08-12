"""Unit tests for `diff_view_attributes` (ticket #79) — built straight
against `Version` objects and DRF handler classes, no schema or HTTP client
involved, the same posture `test_version_composition.py` already takes
toward `resolution_table`."""

from rest_framework import pagination, viewsets
from rest_framework.response import Response

from apiver.drf import Version
from apiver.drf.schema_diff import diff_view_attributes
from tests.testapp.views import PaymentViewSet, PaymentViewSetV2, PingViewSet


def test_no_change_when_the_registration_is_inherited_untouched():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.freeze()
    v2 = v1.derive("v2")

    assert diff_view_attributes(v1, v2) == []


def test_permission_classes_change_is_detected():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.freeze()
    v2 = v1.derive("v2")
    v2.override("payments", PaymentViewSetV2, basename="payments")

    changes = diff_view_attributes(v1, v2)

    by_attribute = {c.attribute: c for c in changes}
    change = by_attribute["permission_classes"]
    assert change.resource == "payments"
    assert change.before == ("rest_framework.permissions.AllowAny",)
    assert change.after == ("rest_framework.permissions.IsAuthenticated",)
    assert change.breaking is True


def test_unrelated_attributes_are_unchanged():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.freeze()
    v2 = v1.derive("v2")
    v2.override("payments", PaymentViewSetV2, basename="payments")

    changes = diff_view_attributes(v1, v2)

    assert {c.attribute for c in changes} == {"permission_classes"}


def test_pagination_class_change_is_detected():
    class PagedV1(viewsets.ViewSet):
        def list(self, request):
            return Response([])

    class PagedV2(viewsets.ViewSet):
        pagination_class = pagination.PageNumberPagination

        def list(self, request):
            return Response([])

    v1 = Version("v1")
    v1.register("items", PagedV1, basename="items")
    v1.freeze()
    v2 = v1.derive("v2")
    v2.override("items", PagedV2, basename="items")

    changes = diff_view_attributes(v1, v2)

    by_attribute = {c.attribute: c for c in changes}
    change = by_attribute["pagination_class"]
    assert change.before is None
    assert change.after == "rest_framework.pagination.PageNumberPagination"


def test_ordering_change_is_detected_as_plain_strings_not_class_refs():
    class OrderedV1(viewsets.ViewSet):
        ordering = ("id",)

        def list(self, request):
            return Response([])

    class OrderedV2(viewsets.ViewSet):
        ordering = ("-created",)

        def list(self, request):
            return Response([])

    v1 = Version("v1")
    v1.register("items", OrderedV1, basename="items")
    v1.freeze()
    v2 = v1.derive("v2")
    v2.override("items", OrderedV2, basename="items")

    changes = diff_view_attributes(v1, v2)

    by_attribute = {c.attribute: c for c in changes}
    change = by_attribute["ordering"]
    assert change.before == ("id",)
    assert change.after == ("-created",)


def test_key_only_present_on_one_side_is_skipped():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.register("ping", PingViewSet, basename="ping")
    v1.freeze()
    v2 = v1.derive("v2")
    v2.remove("ping")

    assert diff_view_attributes(v1, v2) == []


def test_function_based_handlers_are_skipped():
    v1 = Version("v1")
    v1.register("pong", lambda request: None, name="pong")
    v1.freeze()
    v2 = v1.derive("v2")
    v2.override("pong", lambda request: None, name="pong")

    assert diff_view_attributes(v1, v2) == []
