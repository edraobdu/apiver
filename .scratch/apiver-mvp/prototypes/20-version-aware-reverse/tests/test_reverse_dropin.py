"""Is `apiver.reverse` a drop-in for `django.urls.reverse` at the call site?

Patching Django's reverse is impossible (test_patch_binding.py). Replacing calls to it by
hand is a different question entirely — this file asks whether the replacement behaves.
"""

import pytest
from django.urls import reverse as django_reverse
from rest_framework.test import APIRequestFactory

from spike.apiver_core import apiver_reverse, current_version

pytestmark = [pytest.mark.django_db, pytest.mark.urls("spike.urls")]


@pytest.fixture
def serving_v2():
    from spike.v2.registry import v2

    token = current_version.set(v2)
    yield v2
    current_version.reset(token)


# -- shape compatibility -------------------------------------------------------


def test_returns_a_relative_path_just_like_django_reverse(serving_v2):
    """No request supplied — same return shape as django.urls.reverse."""
    url = apiver_reverse("payment-detail", kwargs={"pk": 1})

    assert url.startswith("/")
    assert url == "/api/v2/plain-payments/1/"


def test_returns_an_absolute_uri_when_given_a_request(serving_v2):
    """Superset behaviour: it can also do what DRF's reverse does."""
    request = APIRequestFactory().get("/")
    request.apiver_version = serving_v2
    request.resolver_match = None

    url = apiver_reverse("payment-detail", kwargs={"pk": 1}, request=request)

    assert url.startswith("http://testserver/")
    assert url.endswith("/api/v2/plain-payments/1/")


def test_django_only_keyword_arguments_pass_through(serving_v2):
    """`query` and `fragment` are django.urls.reverse kwargs, not DRF ones."""
    url = apiver_reverse(
        "payment-detail", kwargs={"pk": 1}, query={"expand": "card"}, fragment="top"
    )

    assert url == "/api/v2/plain-payments/1/?expand=card#top"


def test_it_matches_django_reverse_exactly_when_no_version_is_serving():
    """Outside a request there is no version, so it must degrade to plain behaviour."""
    assert apiver_reverse("payment-detail", kwargs={"pk": 1}) == django_reverse(
        "payment-detail", kwargs={"pk": 1}
    )


# -- the classic django.urls.reverse call site ---------------------------------


def test_a_models_get_absolute_url_becomes_version_aware(serving_v2):
    """`get_absolute_url()` takes no request — the ContextVar is what rescues it."""

    class FakePayment:
        pk = 7

        def get_absolute_url(self):
            return apiver_reverse("payment-detail", kwargs={"pk": self.pk})

    assert FakePayment().get_absolute_url() == "/api/v2/plain-payments/7/"


# -- the trap ------------------------------------------------------------------


def test_an_unversioned_name_still_resolves_while_serving_v2(serving_v2):
    """A developer told "replace every reverse()" will also replace the ones pointing at
    non-versioned URLs — the admin, a login page, a webhook. Blind prefixing would turn
    every one of those into NoReverseMatch, so apiver_reverse falls back to the bare name.
    """
    assert apiver_reverse("healthz") == "/healthz/"


def test_the_fallback_does_not_swallow_versioned_names(serving_v2):
    """The fallback must not quietly downgrade a versioned route to the Base Version."""
    assert apiver_reverse("payment-detail", kwargs={"pk": 1}) == "/api/v2/plain-payments/1/"


def test_a_genuinely_unknown_name_still_raises(serving_v2):
    """The fallback must not turn a typo into silence."""
    from django.urls import NoReverseMatch

    with pytest.raises(NoReverseMatch):
        apiver_reverse("no-such-route-anywhere")
