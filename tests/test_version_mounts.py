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
