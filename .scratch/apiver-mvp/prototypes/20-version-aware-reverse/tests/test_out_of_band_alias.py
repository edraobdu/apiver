"""Should out-of-band code (Celery, management commands, cron) link against an Alias?

The claim under test: pointing at `stable` instead of a concrete version means the code
never needs editing when a version ships or retires.
"""

import pytest
from rest_framework.test import APIClient

from payments.models import Payment
from spike import apiver_core
from spike.apiver_core import apiver_reverse

pytestmark = pytest.mark.django_db


@pytest.fixture
def linking_to_stable():
    apiver_core.out_of_band_alias = "stable"
    yield
    apiver_core.out_of_band_alias = None


# -- the default this replaces -------------------------------------------------


@pytest.mark.urls("spike.urls")
def test_without_the_setting_out_of_band_links_point_at_the_oldest_version():
    """The bad default: a Celery task emailing links would send everyone to V1 — the
    version most likely to be deprecated and then start answering 410."""
    assert apiver_reverse("payment-detail", kwargs={"pk": 1}) == "/api/v1/plain-payments/1/"


# -- the proposal --------------------------------------------------------------


@pytest.mark.urls("spike.urls")
def test_out_of_band_links_can_default_to_an_alias(linking_to_stable):
    assert apiver_reverse("payment-detail", kwargs={"pk": 1}) == (
        "/api/stable/plain-payments/1/"
    )


@pytest.mark.urls("spike.urls")
def test_the_alias_link_actually_serves(linking_to_stable):
    payment = Payment.objects.create(amount=1050, currency="USD")

    url = apiver_reverse("payment-detail", kwargs={"pk": payment.pk})
    response = APIClient().get(url)

    assert response.status_code == 200
    assert response.data["id"] == payment.pk


@pytest.mark.urls("spike.urls")
def test_an_in_request_version_still_wins_over_the_out_of_band_default(linking_to_stable):
    """The fallback must not hijack links generated while actually serving V1."""
    payment = Payment.objects.create(amount=1050, currency="USD")

    row = APIClient().get("/api/v1/plain-payments/").data["results"][0]

    assert f"/api/v1/plain-payments/{payment.pk}/" in row["url"]


# -- the payoff: promoting the alias changes nothing in the caller -------------


@pytest.mark.urls("spike.urls")
def test_before_promotion_stable_is_v2(linking_to_stable):
    payment = Payment.objects.create(amount=1050, currency="USD")

    url = apiver_reverse("payment-detail", kwargs={"pk": payment.pk})
    body = APIClient().get(url).data

    assert url == f"/api/stable/plain-payments/{payment.pk}/"
    assert "status" not in body  # V2's shape


@pytest.mark.urls("spike.urls_alias_v3")
def test_after_promotion_the_identical_call_serves_v3(linking_to_stable):
    """Same reverse() argument, same URL string, different implementation behind it.

    This is the whole argument for the recommendation: the Celery task was never edited.
    """
    payment = Payment.objects.create(amount=1050, currency="USD")

    url = apiver_reverse("payment-detail", kwargs={"pk": payment.pk})
    body = APIClient().get(url).data

    assert url == f"/api/stable/plain-payments/{payment.pk}/"
    assert body["status"] == "pending"  # V3's shape


# -- the honest counter-case ---------------------------------------------------


@pytest.mark.urls("spike.urls")
def test_a_persisted_alias_link_silently_changes_meaning_when_stable_moves():
    """The risk the recommendation has to be scoped around.

    A URL written into an email, a webhook registration or a database row is a *stored*
    artifact. If it says /api/stable/, its meaning changes under the holder's feet the
    day stable is promoted — which is right for a navigational link and wrong for a
    contract.
    """
    payment = Payment.objects.create(amount=1050, currency="USD")
    stored_link = f"/api/stable/plain-payments/{payment.pk}/"

    before = APIClient().get(stored_link).data
    assert "status" not in before

    # ... later, stable is promoted to v3. Same stored string, new response shape.
    from django.test import override_settings

    with override_settings(ROOT_URLCONF="spike.urls_alias_v3"):
        after = APIClient().get(stored_link).data

    assert after["status"] == "pending"
    assert before != after  # the stored link did not change; what it returns did


@pytest.mark.urls("spike.urls")
def test_pinning_a_concrete_version_stays_available_for_contracts(linking_to_stable):
    """Opting out has to remain easy for the cases that need a frozen contract."""
    assert apiver_reverse("v2:payment-detail", kwargs={"pk": 1}) == (
        "/api/v2/plain-payments/1/"
    )
