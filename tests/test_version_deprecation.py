from datetime import timedelta

import pytest
from django.utils import timezone
from django.utils.http import http_date
from rest_framework.test import APIClient

from tests.testapp.urls import DEPRECATED_BASE_SUNSET, SUNSET_CLOCK_INSTANT


@pytest.fixture
def client():
    return APIClient()


def test_deprecated_version_carries_deprecation_and_sunset_headers(client):
    response = client.get("/api/deprecated-base/ping/")

    assert response.status_code == 200
    assert response["Deprecation"] == "true"
    assert response["Sunset"] == http_date(DEPRECATED_BASE_SUNSET.timestamp())


def test_non_deprecated_version_carries_neither_header(client):
    response = client.get("/api/v1/ping/")

    assert response.status_code == 200
    assert "Deprecation" not in response
    assert "Sunset" not in response


def test_gating_is_not_special_cased_away_from_the_base_version(client):
    """deprecated-base has no parent — exactly the unnamespaced-base case the
    ticket calls out as broken by a request.resolver_match-based approach."""
    response = client.get("/api/deprecated-base/ping/")

    assert response.status_code == 200
    assert response["Deprecation"] == "true"


def test_sunset_gating_reads_the_live_clock_on_every_request(client, monkeypatch):
    before = SUNSET_CLOCK_INSTANT - timedelta(minutes=1)
    after = SUNSET_CLOCK_INSTANT + timedelta(minutes=1)

    monkeypatch.setattr(timezone, "now", lambda: before)
    response = client.get("/api/sunset-clock/ping/")
    assert response.status_code == 200

    monkeypatch.setattr(timezone, "now", lambda: after)
    response = client.get("/api/sunset-clock/ping/")
    assert response.status_code == 410
    assert response.json() == {"detail": "This API version has been sunset."}


def test_past_sunset_short_circuits_without_reaching_the_view(client, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: SUNSET_CLOCK_INSTANT + timedelta(days=1))

    response = client.get("/api/sunset-clock/ping/")

    assert response.status_code == 410
    assert "Deprecation" not in response
    assert response.json() == {"detail": "This API version has been sunset."}


def test_unmounted_version_is_a_plain_404(client):
    response = client.get("/api/unmounted/ping/")

    assert response.status_code == 404
