import pytest
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
