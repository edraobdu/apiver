"""ADR 0005: links resolve through the Version serving the request.

Uses `tests.testapp.urls`'s `widgets` resource — registered once on v1 and
never touched by v2 or v3 — to prove inheritance composes hyperlink
behaviour, not just routes, and `healthz` — a bare route outside every
Version's mount — to prove `apiver.drf.reverse`'s fallback."""

import threading

import pytest
from django.test import override_settings
from django.urls import reverse as django_reverse
from rest_framework.test import APIClient

from apiver.drf import reverse as apiver_reverse
from apiver.drf.version import current_version


@pytest.fixture
def client():
    return APIClient()


def test_inherited_hyperlinked_field_resolves_within_the_base_version(client):
    response = client.get("/api/v1/widgets/7/")

    assert response.status_code == 200
    assert response.json()["url"] == "http://testserver/api/v1/widgets/7/"


def test_inherited_hyperlinked_field_resolves_within_a_derived_version(client):
    """WidgetViewSet was registered on v1 alone; v2 inherits it unchanged
    and still produces a v2-rooted link (ADR 0005 items 1-3)."""
    response = client.get("/api/v2/widgets/7/")

    assert response.status_code == 200
    assert response.json()["url"] == "http://testserver/api/v2/widgets/7/"


def test_inherited_hyperlinked_field_resolves_within_a_grandchild_version(client):
    response = client.get("/api/v3/widgets/7/")

    assert response.status_code == 200
    assert response.json()["url"] == "http://testserver/api/v3/widgets/7/"


def test_request_through_an_alias_keeps_producing_alias_rooted_links(client):
    """Item 14: a client that deliberately pinned a movable name is not
    silently migrated onto the concrete Version it targets."""
    response = client.get("/api/stable/widgets/7/")

    assert response.status_code == 200
    assert response.json()["url"] == "http://testserver/api/stable/widgets/7/"


def test_wrap_stamps_apiver_version_and_the_contextvar_and_resets_after():
    """Same mount-time wrapper ticket 13's gating already used (ADR 0005
    item 1) — verified from the inside, on a bare callback, rather than by
    re-deriving it from a response's links."""
    from django.http import JsonResponse
    from django.test import RequestFactory

    from tests.testapp.urls import v2

    captured = {}

    def _probe(request):
        captured["apiver_version"] = getattr(request, "apiver_version", None)
        captured["current_version"] = current_version.get()
        return JsonResponse({"ok": True})

    wrapped = v2._wrap(_probe)
    request = RequestFactory().get("/probe/")
    wrapped(request)

    assert captured["apiver_version"] is v2
    assert captured["current_version"] is v2
    assert current_version.get() is None  # reset after the call, not leaked


def test_apiver_reverse_is_a_drop_in_for_djangos_reverse_with_no_request():
    assert apiver_reverse("healthz") == django_reverse("healthz")


def test_apiver_reverse_resolves_within_the_version_stamped_on_the_request(client):
    """A bare reverse() call, given the request, resolves against the
    Version serving it — exactly what a hand-written view or serializer
    method calling apiver.drf.reverse directly would get."""
    response = client.get("/api/v2/widgets/7/")
    assert response.status_code == 200


def test_apiver_reverse_falls_back_to_the_bare_name_for_an_unversioned_route():
    """Item 10: a project that replaced every reverse() call must not get
    NoReverseMatch on a route that was never versioned, while a versioned
    request is being served (simulated here via the ContextVar directly)."""
    from tests.testapp.urls import v2

    token = current_version.set(v2)
    try:
        assert apiver_reverse("healthz") == "/healthz/"
    finally:
        current_version.reset(token)


def test_apiver_reverse_out_of_band_falls_back_to_the_configured_alias():
    """Item 11: with no request and no ContextVar, out-of-band code (a
    Celery task, a management command) links against the configured Alias
    rather than silently resolving to the oldest, unnamespaced Base
    Version."""
    with override_settings(APIVER_OUT_OF_BAND_ALIAS="stable"):
        assert apiver_reverse("widgets-detail", kwargs={"pk": "7"}) == "/api/stable/widgets/7/"


def test_apiver_reverse_out_of_band_with_no_alias_configured_uses_the_bare_name():
    assert apiver_reverse("widgets-detail", kwargs={"pk": "7"}) == "/api/v1/widgets/7/"


def test_hyperlink_patch_is_disabled_by_the_escape_hatch_setting(client):
    with override_settings(APIVER_PATCH_HYPERLINKED_FIELDS=False):
        response = client.get("/api/v2/widgets/7/")

    assert response.status_code == 200
    # DRF's own, unpatched reverse() has no notion of a serving Version, so
    # it resolves the bare (v1) name regardless of which mount served it.
    assert response.json()["url"] == "http://testserver/api/v1/widgets/7/"


def test_contextvar_does_not_leak_across_concurrent_requests(client):
    """Not a threadlocal, so correctness doesn't depend on one request per
    thread staying pinned to that thread for its whole lifetime (ADR 0005
    item 2)."""
    results = {}

    def _hit(version_path, key):
        response = APIClient().get(f"/api/{version_path}/widgets/7/")
        results[key] = response.json()["url"]

    threads = [
        threading.Thread(target=_hit, args=("v1", "v1")),
        threading.Thread(target=_hit, args=("v2", "v2")),
        threading.Thread(target=_hit, args=("v3", "v3")),
        threading.Thread(target=_hit, args=("stable", "stable")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results["v1"] == "http://testserver/api/v1/widgets/7/"
    assert results["v2"] == "http://testserver/api/v2/widgets/7/"
    assert results["v3"] == "http://testserver/api/v3/widgets/7/"
    assert results["stable"] == "http://testserver/api/stable/widgets/7/"
