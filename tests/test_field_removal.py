import pytest
from rest_framework import serializers

from apiver.drf import Version
from apiver.drf.fields import check_no_removed_fields
from tests.testapp.views import (
    BrokenInvoiceViewSetV2,
    InvoiceViewSet,
    InvoiceViewSetV2,
    PingViewSet,
    RedactedInvoiceViewSetV2,
)


def test_register_raises_when_serializer_sets_a_field_to_none():
    v1 = Version("v1")

    with pytest.raises(ValueError):
        v1.register("invoices", BrokenInvoiceViewSetV2, basename="invoices")


def test_override_raises_when_serializer_sets_a_field_to_none():
    v1 = Version("v1")
    v1.register("invoices", InvoiceViewSet, basename="invoices")
    v2 = v1.derive("v2")

    with pytest.raises(ValueError):
        v2.override("invoices", BrokenInvoiceViewSetV2, basename="invoices")


def test_meta_fields_surgery_registers_cleanly():
    v1 = Version("v1")
    v1.register("invoices", InvoiceViewSet, basename="invoices")
    v2 = v1.derive("v2")

    v2.override("invoices", InvoiceViewSetV2, basename="invoices")

    route = v2.resolution_table["^invoices/(?P<pk>[^/.]+)/$"]
    assert route.registration.handler is InvoiceViewSetV2


def test_del_self_fields_fallback_registers_cleanly():
    v1 = Version("v1")
    v2 = v1.derive("v2")

    v2.register("invoices-redacted", RedactedInvoiceViewSetV2, basename="invoices-redacted")

    assert "^invoices-redacted/(?P<pk>[^/.]+)/$" in v2.resolution_table


def test_a_handler_with_no_serializer_class_is_unaffected_by_the_guard():
    v1 = Version("v1")

    v1.register("ping", PingViewSet, basename="ping")

    assert "^ping/$" in v1.resolution_table


def test_the_guard_walks_the_full_mro_not_just_the_immediate_parent():
    class Base(serializers.Serializer):
        secret = serializers.CharField()

    class Mid(Base):
        pass

    class Grand(Mid):
        secret = None

    with pytest.raises(ValueError):
        check_no_removed_fields(Grand)


def test_redeclaring_a_field_as_a_real_field_is_not_a_removal():
    class Base(serializers.Serializer):
        secret = serializers.CharField()

    class Overridden(Base):
        secret = serializers.IntegerField()

    check_no_removed_fields(Overridden)


def test_a_non_serializer_class_is_ignored():
    class NotASerializer:
        secret = None

    check_no_removed_fields(NotASerializer)
