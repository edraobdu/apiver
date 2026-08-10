import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


def test_registered_viewset_answers_a_real_request(client):
    response = client.get("/api/v1/ping/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unregistered_path_is_not_found(client):
    response = client.get("/api/v1/nope/")

    assert response.status_code == 404


def test_viewset_detail_route_answers_a_real_request(client):
    response = client.get("/api/v1/payments/42/")

    assert response.status_code == 200
    assert response.json() == {"id": "42"}


def test_explicit_view_path_is_not_swallowed_by_the_viewset_detail_route(client):
    response = client.get("/api/v1/payments/summary/")

    assert response.status_code == 200
    assert response.json() == {"summary": "ok"}


def test_api_view_function_answers_a_real_request(client):
    response = client.get("/api/v1/pong/")

    assert response.status_code == 200
    assert response.json() == {"status": "pong"}


def test_plain_django_view_answers_a_real_request(client):
    response = client.get("/api/v1/plain-ping/")

    assert response.status_code == 200
    assert response.json() == {"status": "plain"}


def test_derived_version_serves_a_route_it_never_registered_itself(client):
    """V2 never registered payments/ — it inherits it live from V1 (ticket 08)."""
    response = client.get("/api/v2/payments/42/")

    assert response.status_code == 200
    assert response.json() == {"id": "42"}


def test_derived_version_serves_a_route_it_registered_itself(client):
    response = client.get("/api/v2/refunds/")

    assert response.status_code == 200
    assert response.json() == {"results": ["r1"]}


def test_a_route_added_only_to_the_derived_version_is_not_served_by_the_base(client):
    response = client.get("/api/v1/refunds/")

    assert response.status_code == 404


def test_base_version_reverse_uses_bare_names_and_resolves_to_the_base_mount():
    assert reverse("payments-detail", args=["42"]) == "/api/v1/payments/42/"


def test_derived_version_reverse_is_namespaced_and_resolves_to_its_own_mount():
    assert reverse("v2:payments-detail", args=["42"]) == "/api/v2/payments/42/"


def test_overridden_resource_serves_the_new_shape_under_the_child(client):
    response = client.get("/api/v3/payments/42/")

    assert response.status_code == 200
    assert response.json() == {"id": "42", "version": "v2"}


def test_overridden_resource_still_serves_the_old_shape_under_the_parent(client):
    response = client.get("/api/v1/payments/42/")

    assert response.status_code == 200
    assert response.json() == {"id": "42"}


def test_override_that_drops_a_route_leaves_no_stale_parent_path_behind(client):
    """PaymentViewSetV2 has no list action, so /api/v3/payments/ must not
    fall through to the parent's list route (ADR 0001 item 3)."""
    response = client.get("/api/v3/payments/")

    assert response.status_code == 404


def test_removed_resource_404s_under_the_child(client):
    response = client.get("/api/v3/ping/")

    assert response.status_code == 404


def test_removed_resource_still_serves_under_the_parent(client):
    response = client.get("/api/v2/ping/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
