import pytest
import yaml
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


def _schema(client, version):
    response = client.get(f"/api/{version}/schema/")
    assert response.status_code == 200
    return yaml.safe_load(response.content)


def test_v1_invoice_response_still_carries_internal_note():
    """The 'before' shape (ticket 08 baseline): V1 never removed anything,
    so internal_note is still there — the control this ticket's idioms are
    measured against."""
    response = APIClient().get("/api/v1/invoices/INV-1/")

    assert response.status_code == 200
    assert response.json() == {
        "number": "INV-1",
        "amount": "10.00",
        "internal_note": "do not expose to clients",
    }


def test_meta_fields_surgery_drops_the_field_from_the_response_body(client):
    response = client.get("/api/v2/invoices/INV-1/")

    assert response.status_code == 200
    assert response.json() == {"number": "INV-1", "amount": "10.00"}


def test_meta_fields_surgery_drops_the_field_from_the_schema(client):
    doc = _schema(client, "v2")

    schema = doc["components"]["schemas"]["InvoiceV2"]
    assert "internal_note" not in schema["properties"]
    assert set(schema["properties"]) == {"number", "amount"}


def test_del_self_fields_drops_the_field_from_the_response_body(client):
    response = client.get("/api/v2/invoices-redacted/INV-1/")

    assert response.status_code == 200
    assert response.json() == {"number": "INV-1", "amount": "10.00"}


def test_del_self_fields_drops_the_field_from_the_schema(client):
    doc = _schema(client, "v2")

    schema = doc["components"]["schemas"]["RedactedInvoiceV2"]
    assert "internal_note" not in schema["properties"]
    assert set(schema["properties"]) == {"number", "amount"}


def test_v1_flag_action_still_serves():
    response = APIClient().get("/api/v1/invoices/INV-1/flag/")

    assert response.status_code == 200
    assert response.json() == {"flagged": True}


def test_action_none_removes_the_action_cleanly_and_it_404s(client):
    """The asymmetry this ticket calls out: unlike field = None,
    action = None is the correct, unadorned idiom — get_extra_actions()
    drops it from the router with no crash and no silent survival."""
    response = client.get("/api/v2/invoices/INV-1/flag/")

    assert response.status_code == 404


def test_action_none_removes_the_action_from_the_schema_too(client):
    doc = _schema(client, "v2")

    assert "/api/v2/invoices/{id}/flag/" not in doc["paths"]
