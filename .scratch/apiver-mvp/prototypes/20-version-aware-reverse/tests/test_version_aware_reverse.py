"""Prototype for GitHub ticket #20 — intra-version hyperlinking.

Question under test: can a view/serializer inherited from V1 into V2 produce V2-rooted
URLs without V2 redeclaring anything, by stamping the serving Version at mount time?

Contrasted throughout with the register-time class-stamping alternative.
"""

import pytest
from rest_framework.test import APIClient

from payments.models import Payment

pytestmark = [pytest.mark.django_db, pytest.mark.urls("spike.urls")]


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def payment():
    return Payment.objects.create(amount=1050, currency="USD")


# -- the bug, confirmed --------------------------------------------------------


def test_naive_hyperlink_inherited_into_v2_still_points_at_v1(client, payment):
    """The failure mode ADR 0001 flagged and left unsettled."""
    response = client.get("/api/v2/naive-payments/")
    row = response.data["results"][0]

    assert response.status_code == 200
    assert "/api/v1/" in row["url"]
    assert "/api/v2/" not in row["url"]


def test_naive_serializer_method_reverse_inherited_into_v2_also_points_at_v1(client, payment):
    """Not just HyperlinkedIdentityField — any bare reverse() in inherited code."""
    row = client.get("/api/v2/naive-payments/").data["results"][0]

    assert "/api/v1/" in row["receipt_link"]


# -- the proposed fix ----------------------------------------------------------


def test_versioned_hyperlink_inherited_into_v2_points_at_v2(client, payment):
    """V2's registry never mentions `payments`. The link is still V2-rooted."""
    response = client.get("/api/v2/payments/")
    row = response.data["results"][0]

    assert response.status_code == 200
    assert f"/api/v2/payments/{payment.pk}/" in row["url"]


def test_versioned_hyperlink_under_v1_still_points_at_v1(client, payment):
    """The same serializer object, served under the Base Version, stays unnamespaced."""
    row = client.get("/api/v1/payments/").data["results"][0]

    assert f"/api/v1/payments/{payment.pk}/" in row["url"]


def test_versioned_serializer_method_reverse_follows_the_serving_version(client, payment):
    v1_row = client.get("/api/v1/payments/").data["results"][0]
    v2_row = client.get("/api/v2/payments/").data["results"][0]

    assert "/api/v1/payments/" in v1_row["receipt_link"]
    assert "/api/v2/payments/" in v2_row["receipt_link"]


def test_generated_links_actually_resolve(client, payment):
    """A link that 404s would make the whole mechanism worthless."""
    url = client.get("/api/v2/payments/").data["results"][0]["url"]

    followed = client.get(url)

    assert followed.status_code == 200
    assert followed.data["id"] == payment.pk


# -- arbitrary logic can read the Version, not just reverse() ------------------


def test_serializer_can_read_the_serving_version_object(client, payment):
    v1_row = client.get("/api/v1/payments/").data["results"][0]
    v2_row = client.get("/api/v2/payments/").data["results"][0]

    assert v1_row["served_by"] == "v1"
    assert v2_row["served_by"] == "v2"


def test_view_can_read_the_serving_version_object(client):
    assert client.get("/api/v1/payments/whoami/").data["stamped_on_request"] == "v1"
    assert client.get("/api/v2/payments/whoami/").data["stamped_on_request"] == "v2"


# -- why register-time stamping cannot work ------------------------------------


def test_register_time_class_stamp_reports_the_wrong_version_under_v2(client):
    """The class was stamped once, by V1. V2 inherits that same class object."""
    v1_body = client.get("/api/v1/payments/whoami/").data
    v2_body = client.get("/api/v2/payments/whoami/").data

    assert v1_body["stamped_at_register"] == "v1"
    assert v2_body["stamped_at_register"] == "v1"  # served under v2, reports v1
    assert v2_body["stamped_on_request"] == "v2"  # the mount-time stamp is right


def test_one_viewset_class_object_serves_both_versions():
    """The root cause, asserted directly rather than inferred."""
    from spike.v1.registry import v1
    from spike.v2.registry import v2

    v1_reg = v1.resolution_table()["payments"]
    v2_reg = v2.resolution_table()["payments"]

    assert v1_reg is v2_reg
    assert v1_reg.handler is v2_reg.handler


# -- aliases -------------------------------------------------------------------


def test_alias_requests_produce_alias_rooted_links(client, payment):
    """A client that came in via /api/stable/ should not be handed /api/v2/ links."""
    row = client.get("/api/stable/payments/").data["results"][0]

    assert "/api/stable/payments/" in row["url"]
    assert "/api/v2/" not in row["url"]


def test_alias_still_reports_the_concrete_version_it_targets(client):
    """The link root follows the alias; the Version identity is still v2."""
    assert client.get("/api/stable/payments/whoami/").data["stamped_on_request"] == "v2"


def test_alias_reuses_the_targets_exact_callback_objects():
    from spike.v2.registry import v2

    from spike.apiver_core import Alias

    alias = Alias("stable", target=v2)

    assert alias.urls[0] is v2.urlpatterns()


# -- the wrapper must stay transparent -----------------------------------------


def test_wrapper_preserves_the_drf_attributes_route_identity_depends_on():
    """ADR 0001 reads `.cls`/`.initkwargs`/`.actions`; drf-spectacular reads them too.

    If the mount-time wrapper hid these, it would break route identity and schema
    generation at once.
    """
    from spike.v2.registry import v2

    callbacks = [p.callback for p in v2.urlpatterns()]
    viewset_callbacks = [c for c in callbacks if hasattr(c, "actions")]

    assert viewset_callbacks, "expected at least one viewset-backed callback"
    for callback in viewset_callbacks:
        assert callback.cls is not None
        assert isinstance(callback.initkwargs, dict)
        assert isinstance(callback.actions, dict)


def test_v2_delta_still_applies(client):
    """Sanity: the override V2 actually declares still works."""
    from users.models import UserProfile

    UserProfile.objects.create(username="ada", email="ada@example.com")

    v1_row = client.get("/api/v1/users/").data["results"][0]
    v2_row = client.get("/api/v2/users/").data["results"][0]

    assert "email" in v1_row
    assert "email" not in v2_row
