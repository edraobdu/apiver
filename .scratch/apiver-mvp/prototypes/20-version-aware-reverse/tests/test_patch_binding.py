"""Why the `get_url` patch has no import-order problem and the `reverse` patch does.

The difference is early vs late binding, and it decides which interception points a
library can safely own.
"""

import pytest
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework.test import APIRequestFactory

from spike import zero_pain
from spike.apiver_core import current_version
from users.models import UserProfile

pytestmark = [pytest.mark.django_db, pytest.mark.urls("spike.urls")]


@pytest.fixture
def v2_request():
    from spike.v2.registry import v2

    request = APIRequestFactory().get("/")
    request.apiver_version = v2
    request.resolver_match = None
    return request


# -- late binding: the class method is looked up at call time ------------------


def test_a_field_instantiated_before_the_patch_still_picks_it_up(v2_request):
    """The developer's serializer was imported and its fields built long ago.

    `self.get_url(...)` resolves through the class at *call* time, so a field object
    created before the patch landed still routes into the patched method. This is why
    the hyperlink fix has no import-order dependence at all.
    """
    user = UserProfile.objects.create(username="ada", email="a@example.com")
    field = HyperlinkedIdentityField(view_name="userprofile-detail")  # built first

    unpatched = field.get_url(user, "userprofile-detail", v2_request, None)
    zero_pain.install()
    try:
        patched = field.get_url(user, "userprofile-detail", v2_request, None)
    finally:
        zero_pain.uninstall()

    assert "/api/v1/plain-users/" in unpatched
    assert "/api/v2/plain-users/" in patched  # same object, now correct


def test_a_developers_own_field_subclass_defined_before_the_patch_is_covered(v2_request):
    """Subclasses inherit through the MRO, which is also resolved at call time."""

    class MyCustomLink(HyperlinkedIdentityField):
        pass

    user = UserProfile.objects.create(username="grace", email="g@example.com")
    field = MyCustomLink(view_name="userprofile-detail")

    zero_pain.install()
    try:
        url = field.get_url(user, "userprofile-detail", v2_request, None)
    finally:
        zero_pain.uninstall()

    assert "/api/v2/plain-users/" in url


def test_a_subclass_that_overrides_get_url_is_correctly_not_covered(v2_request):
    """The one real gap, and it is the right behaviour — the developer took control."""

    class HandRolledLink(HyperlinkedIdentityField):
        def get_url(self, obj, view_name, request, format):
            from rest_framework.reverse import reverse

            return reverse(view_name, kwargs={"pk": obj.pk}, request=request)

    user = UserProfile.objects.create(username="ada", email="a@example.com")
    field = HandRolledLink(view_name="userprofile-detail")

    zero_pain.install()
    try:
        url = field.get_url(user, "userprofile-detail", v2_request, None)
    finally:
        zero_pain.uninstall()

    assert "/api/v1/plain-users/" in url  # bypassed the patch by overriding it


# -- early binding: why django.urls.reverse cannot be reached ------------------


def test_patching_django_urls_reverse_does_not_even_reach_drfs_reverse():
    """rest_framework/reverse.py line 5: `from django.urls import reverse as django_reverse`.

    That name was bound when DRF was imported. Rebinding `django.urls.reverse` afterwards
    changes nothing for DRF — so the patch cannot even reach the library sitting directly
    on top of it, let alone arbitrary user code.
    """
    import django.urls
    import rest_framework.reverse

    sentinel_called = []

    def sentinel(*args, **kwargs):
        sentinel_called.append(True)
        return "/sentinel/"

    original = django.urls.reverse
    django.urls.reverse = sentinel
    try:
        rest_framework.reverse.reverse("payment-detail", kwargs={"pk": 1})
    finally:
        django.urls.reverse = original

    assert sentinel_called == []  # DRF never consulted the patched name


def test_django_reverse_has_no_request_to_scope_a_rewrite_with():
    """Even ignoring binding: the signature carries no request and no self.

    A ContextVar could supply the version, but the name being reversed might belong to
    the admin, to auth, or to any third-party app — all of which share this one function.
    Rewriting blindly would break them.
    """
    import inspect

    from django.urls import reverse as django_reverse

    params = set(inspect.signature(django_reverse).parameters)

    assert "request" not in params
    assert "current_app" in params  # the only scoping hook, and it needs an app_name


def test_a_scoped_rewrite_would_still_have_to_know_which_names_are_apivers(v2_request):
    """The scoping apiver *could* do, shown to be possible but not sufficient.

    apiver holds the resolution table, so it can tell its own route names from the
    admin's. That solves safety — but not binding, which the test above already killed.
    """
    from spike.v2.registry import v2

    apiver_names = {
        reg.basename for reg in v2.resolution_table().values() if reg.basename
    }

    assert "payment" in apiver_names
    assert "admin" not in apiver_names


# -- the recommended path needs no patching at all -----------------------------


def test_apiver_reverse_works_with_no_patching_whatsoever():
    """What developers would be asked to call instead. No monkeypatching involved."""
    from spike.apiver_core import apiver_reverse
    from spike.v2.registry import v2

    token = current_version.set(v2)
    try:
        assert apiver_reverse("payment-detail", kwargs={"pk": 1}) == (
            "/api/v2/plain-payments/1/"
        )
    finally:
        current_version.reset(token)
