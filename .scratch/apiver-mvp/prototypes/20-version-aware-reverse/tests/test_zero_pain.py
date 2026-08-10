"""Can version-aware linking be free for the developer?

Everything here exercises `spike/plain/serializers.py`, which imports nothing from apiver
and is never modified. The only variable is whether apiver's patch is installed.
"""

import pytest
from rest_framework.test import APIClient, APIRequestFactory

from payments.models import Payment
from spike import zero_pain
from users.models import UserProfile

pytestmark = [pytest.mark.django_db, pytest.mark.urls("spike.urls")]


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def payment():
    return Payment.objects.create(amount=1050, currency="USD")


@pytest.fixture
def patched():
    """Install for the duration of one test, always removed afterwards."""
    zero_pain.install()
    yield
    zero_pain.uninstall()


# -- the pain, before ----------------------------------------------------------


def test_unpatched_plain_serializer_leaks_v1_links_under_v2(client, payment):
    row = client.get("/api/v2/plain-payments/").data["results"][0]

    assert "/api/v1/plain-payments/" in row["url"]
    assert "/api/v2/" not in row["url"]


# -- the pain, after -----------------------------------------------------------


def test_patched_plain_serializer_produces_v2_links_under_v2(client, payment, patched):
    """Zero changes to the serializer. The `url` field isn't even declared in it."""
    row = client.get("/api/v2/plain-payments/").data["results"][0]

    assert f"/api/v2/plain-payments/{payment.pk}/" in row["url"]


def test_patched_plain_serializer_still_produces_v1_links_under_v1(client, payment, patched):
    row = client.get("/api/v1/plain-payments/").data["results"][0]

    assert f"/api/v1/plain-payments/{payment.pk}/" in row["url"]


def test_patched_plain_serializer_follows_an_alias(client, payment, patched):
    row = client.get("/api/stable/plain-payments/").data["results"][0]

    assert f"/api/stable/plain-payments/{payment.pk}/" in row["url"]


def test_patched_links_actually_resolve(client, payment, patched):
    url = client.get("/api/v2/plain-payments/").data["results"][0]["url"]

    followed = client.get(url)

    assert followed.status_code == 200
    assert followed.data["id"] == payment.pk


def test_nested_hyperlinked_serializer_is_covered_too(client, patched):
    """Nesting goes through the same get_url, so it should need no extra handling."""
    UserProfile.objects.create(username="ada", email="ada@example.com")

    row = client.get("/api/v2/plain-users/").data["results"][0]

    assert "/api/v2/plain-users/" in row["url"]


def test_hyperlinked_related_field_shares_the_same_patch_point(patched):
    """HyperlinkedIdentityField subclasses HyperlinkedRelatedField, which defines get_url."""
    from rest_framework.relations import HyperlinkedRelatedField

    from spike.v2.registry import v2

    user = UserProfile.objects.create(username="grace", email="g@example.com")
    request = APIRequestFactory().get("/")
    request.apiver_version = v2
    request.resolver_match = None

    field = HyperlinkedRelatedField(view_name="userprofile-detail", read_only=True)
    url = field.get_url(user, "userprofile-detail", request, None)

    assert "/api/v2/plain-users/" in url


# -- what the patch does NOT fix ----------------------------------------------


def test_bare_reverse_in_a_method_field_is_not_fixed_by_the_patch(client, payment, patched):
    """The residue. `reverse()` is a free function — there is no `self` to intercept."""
    row = client.get("/api/v2/plain-payments/").data["results"][0]

    assert "/api/v1/plain-payments/" in row["receipt_link"]  # still wrong
    assert "/api/v2/" in row["url"]  # while the hyperlink beside it is right


# -- safety: does the patch harm a project that never adopted apiver? ----------


@pytest.mark.urls("config.urls")
def test_patch_is_inert_on_a_urlconf_with_no_versions(patched):
    """The reference project's own urlconf — no apiver, no stamp, no namespaces."""
    from rest_framework.relations import HyperlinkedIdentityField

    payment = Payment.objects.create(amount=42, currency="EUR")
    request = APIRequestFactory().get("/")

    field = HyperlinkedIdentityField(view_name="payments-detail")
    url = field.get_url(payment, "payments-detail", request, None)

    assert url.endswith(f"/api/payments/{payment.pk}/")


def test_install_is_idempotent(patched):
    assert zero_pain.install() is False


def test_uninstall_restores_original_behaviour(client, payment):
    zero_pain.install()
    zero_pain.uninstall()

    row = client.get("/api/v2/plain-payments/").data["results"][0]

    assert "/api/v1/plain-payments/" in row["url"]


def test_schema_generation_is_unaffected_by_the_patch(patched):
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator(urlconf="spike.urls").get_schema(request=None, public=True)

    assert "/api/v2/plain-payments/{id}/" in schema["paths"]
