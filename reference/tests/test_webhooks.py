"""Exercises the deepest URL mount in the project, a write-only field, a custom
per-field validator, and a custom exception with a non-standard error shape."""

import pytest
from rest_framework.test import APIClient

from webhooks.models import WebhookEndpoint


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_create_accepts_https_target(client):
    response = client.post(
        "/api/integrations/webhooks/",
        {"target_url": "https://example.com/hook", "event_type": "order.created", "secret": "s3cr3t"},
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_create_rejects_non_https_target(client):
    response = client.post(
        "/api/integrations/webhooks/",
        {"target_url": "http://example.com/hook", "event_type": "order.created", "secret": "s3cr3t"},
    )

    assert response.status_code == 400
    assert "target_url" in response.data


@pytest.mark.django_db
def test_secret_is_accepted_on_write_but_never_returned(client):
    create = client.post(
        "/api/integrations/webhooks/",
        {"target_url": "https://example.com/hook", "event_type": "order.created", "secret": "s3cr3t"},
    )
    assert "secret" not in create.data

    listed = client.get("/api/integrations/webhooks/").data["results"][0]
    assert "secret" not in listed


@pytest.mark.django_db
def test_delivery_test_succeeds_for_an_active_endpoint(client):
    webhook = WebhookEndpoint.objects.create(
        target_url="https://example.com/hook", event_type="order.created", secret="s3cr3t", is_active=True
    )

    response = client.post(f"/api/integrations/webhooks/{webhook.pk}/test-delivery/")

    assert response.status_code == 200
    assert response.data == {"delivered": True, "target_url": "https://example.com/hook"}


@pytest.mark.django_db
def test_delivery_test_fails_with_a_non_standard_error_shape_for_an_inactive_endpoint(client):
    webhook = WebhookEndpoint.objects.create(
        target_url="https://example.com/hook", event_type="order.created", secret="s3cr3t", is_active=False
    )

    response = client.post(f"/api/integrations/webhooks/{webhook.pk}/test-delivery/")

    assert response.status_code == 422
    # Not DRF's usual {"detail": ...} — a genuinely different shape (ADR-worthy
    # if apiver ever needs to reason about error bodies, per catalogue row 19).
    assert response.data == {
        "error": "delivery_failed",
        "target_url": "https://example.com/hook",
        "reason": "endpoint is inactive",
    }


@pytest.mark.django_db
def test_webhooks_are_mounted_two_segments_deeper_than_every_other_resource(client):
    webhook = WebhookEndpoint.objects.create(
        target_url="https://example.com/hook", event_type="order.created", secret="s3cr3t"
    )

    response = client.get(f"/api/integrations/webhooks/{webhook.pk}/")

    assert response.status_code == 200
