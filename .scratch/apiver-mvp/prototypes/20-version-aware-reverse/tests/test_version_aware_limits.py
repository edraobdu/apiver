"""Where the mount-time stamp stops working, and what it costs elsewhere.

Green tests prove the happy path; these exist to find the edges before a design
decision is written on top of them.
"""

import types

import pytest
from rest_framework.test import APIClient

from payments.models import Payment
from spike.apiver_core import apiver_reverse, namespace_for

pytestmark = [pytest.mark.django_db, pytest.mark.urls("spike.urls")]


# -- which of the two sources actually drives URL namespacing? -----------------


def test_resolver_match_alone_is_enough_to_namespace_a_url():
    """No stamped version at all — just the namespace Django already matched."""
    request = types.SimpleNamespace(
        resolver_match=types.SimpleNamespace(namespace="v2"),
    )

    assert namespace_for(request) == "v2"


def test_the_stamp_alone_is_enough_when_resolver_match_is_absent():
    """The path taken outside request/response — no resolver_match yet."""
    version = types.SimpleNamespace(namespace="v2")
    request = types.SimpleNamespace(resolver_match=None, apiver_version=version)

    assert namespace_for(request) == "v2"


def test_base_version_produces_no_namespace_from_either_source():
    """The Base Version keeps bare names, so both sources must agree on 'no prefix'."""
    from spike.v1.registry import v1

    matched = types.SimpleNamespace(resolver_match=types.SimpleNamespace(namespace=""))
    stamped = types.SimpleNamespace(resolver_match=None, apiver_version=v1)

    assert namespace_for(matched) is None or namespace_for(matched) == ""
    assert namespace_for(stamped) is None


# -- the limitation ------------------------------------------------------------


def test_reverse_with_no_request_silently_falls_back_to_the_base_version():
    """The honest edge: `reverse()` outside a request cycle cannot know the Version.

    A Celery task, a management command, a `get_absolute_url()` on a model — none of
    them have a request, so none of them can be version-aware by this mechanism. It
    resolves to the Base Version's bare name, quietly.
    """
    url = apiver_reverse("payments-detail", kwargs={"pk": 1}, request=None)

    assert url == "/api/v1/payments/1/"
    assert "/api/v2/" not in url


def test_serializing_without_a_request_raises_rather_than_emitting_a_wrong_link(
    client_free_payment,
):
    """Better than predicted: DRF refuses outright instead of guessing a version.

    The hyperlink path fails *loudly* with no request in context, so the silent
    fallback above can only bite plain `reverse()` calls, never a hyperlink field.
    """
    from spike.v1.serializers import PaymentV1Serializer

    with pytest.raises(AssertionError, match="requires the request in the serializer"):
        PaymentV1Serializer(client_free_payment, context={}).data


@pytest.fixture
def client_free_payment():
    return Payment.objects.create(amount=200, currency="EUR")


# -- what the wrapper costs ----------------------------------------------------


def test_schema_generation_survives_the_mount_time_wrapper():
    """drf-spectacular reads `callback.cls`; if the wrapper hid it, the schema empties."""
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator(urlconf="spike.urls").get_schema(request=None, public=True)
    paths = set(schema["paths"])

    assert "/api/v2/payments/{id}/" in paths
    assert "/api/v1/payments/{id}/" in paths


def test_the_wrapper_does_not_break_ordinary_request_handling(payment_and_client):
    payment, client = payment_and_client

    detail = client.get(f"/api/v2/payments/{payment.pk}/")

    assert detail.status_code == 200
    assert detail.data["currency"] == "USD"


@pytest.fixture
def payment_and_client():
    return Payment.objects.create(amount=1050, currency="USD"), APIClient()
