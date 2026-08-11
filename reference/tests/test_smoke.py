"""Confidence that the reference project actually runs — not a spec for a library
that doesn't exist yet. Each endpoint gets exercised once."""

import pytest
from rest_framework.test import APIClient

from legacy.models import LegacyInvoice
from orders.models import Order
from payments.models import Payment
from users.models import UserProfile


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_users_crud(client):
    response = client.post(
        "/api/v1/users/", {"username": "ada", "email": "ada@example.com", "full_name": "Ada Lovelace"}
    )
    assert response.status_code == 201
    assert client.get("/api/v1/users/").status_code == 200


@pytest.mark.django_db
def test_payments_list_shows_display_amount(client):
    Payment.objects.create(amount=1050, currency="USD")

    response = client.get("/api/v1/payments/")

    assert response.status_code == 200
    assert response.data["results"][0]["display_amount"] == "10.50 USD"


@pytest.mark.django_db
def test_payments_refund_action(client):
    from django.contrib.auth.models import User

    client.force_authenticate(user=User.objects.create(username="staff"))
    payment = Payment.objects.create(amount=500, currency="USD", status="completed")

    response = client.post(f"/api/v1/payments/{payment.id}/refund/")

    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.status == "failed"


@pytest.mark.django_db
def test_payments_summary_route_is_not_swallowed_by_the_router_detail_pattern(client):
    Payment.objects.create(amount=100, currency="USD")
    Payment.objects.create(amount=200, currency="USD")

    response = client.get("/api/v1/payments/summary/")

    assert response.status_code == 200
    assert response.data == {"total": 300, "count": 2}


@pytest.mark.django_db
def test_orders_crud(client):
    Order.objects.create(reference="ORD-1")

    response = client.get("/api/v1/orders/")

    assert response.status_code == 200
    assert response.data["results"][0]["reference"] == "ORD-1"


@pytest.mark.django_db
def test_legacy_invoices_exist_in_v1(client):
    LegacyInvoice.objects.create(number="INV-1", amount=999)

    response = client.get("/api/v1/legacy-invoices/")

    assert response.status_code == 200
    assert response.data["results"][0]["number"] == "INV-1"


def test_healthz(client):
    response = client.get("/api/v1/healthz/")

    assert response.status_code == 200
    assert response.data == {"status": "ok"}


@pytest.mark.django_db
def test_schema_generates_without_error(client):
    response = client.get("/api/v1/schema/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.oai.openapi")


def test_docs_page_renders(client):
    """Regression: TEMPLATES wasn't configured, so drf_spectacular's bundled
    swagger_ui.html template was never discoverable and this 500'd."""
    response = client.get("/api/v1/docs/")

    assert response.status_code == 200
