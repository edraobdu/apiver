"""The acceptance proof for issue #22: every catalogued change-shape v2 authors,
asserted in a response body or a served schema document, with v1 as the control
proving the same underlying data still serves the old shape unchanged — the two
versions are composed side by side from the same handlers, not copied.

Rows covered: 5 (rename), 6 (remove), 9 (flat->nested), 10 (SerializerMethodField
output change), 12 (whole-resource removal), 13 (URL prefix change), 14b (@action
removal). See api/v2/serializers.py and api/v2/views.py for the idiom each uses.
"""

import re

import pytest
from rest_framework.test import APIClient

from legacy.models import LegacyInvoice
from orders.models import Order
from payments.models import Payment
from users.models import UserProfile
from webhooks.models import WebhookEndpoint


@pytest.fixture
def client():
    return APIClient()


def _schema_paths(client, version):
    response = client.get(f"/api/{version}/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    return response.json()["paths"]


def _schema_properties(client, version, component):
    response = client.get(f"/api/{version}/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    return response.json()["components"]["schemas"][component]["properties"]


# --- row 5: field rename (users: full_name -> display_name) ---------------------


@pytest.mark.django_db
def test_v1_user_response_still_carries_full_name(client):
    user = UserProfile.objects.create(username="ada", email="ada@example.com", full_name="Ada Lovelace")

    response = client.get(f"/api/v1/users/{user.pk}/")

    assert response.status_code == 200
    assert response.data["full_name"] == "Ada Lovelace"
    assert "display_name" not in response.data


@pytest.mark.django_db
def test_v2_user_response_carries_display_name_not_full_name(client):
    user = UserProfile.objects.create(username="ada", email="ada@example.com", full_name="Ada Lovelace")

    response = client.get(f"/api/v2/users/{user.pk}/")

    assert response.status_code == 200
    assert response.data["display_name"] == "Ada Lovelace"
    assert "full_name" not in response.data


def test_v2_user_schema_has_display_name_not_full_name(client):
    properties = _schema_properties(client, "v2", "UserSerializerV2")

    assert "display_name" in properties
    assert "full_name" not in properties


# --- row 6: field removal (orders: status) --------------------------------------


@pytest.mark.django_db
def test_v1_order_response_still_carries_status(client):
    order = Order.objects.create(reference="ORD-1", status="shipped")

    response = client.get(f"/api/v1/orders/{order.pk}/")

    assert response.status_code == 200
    assert response.data["status"] == "shipped"


@pytest.mark.django_db
def test_v2_order_response_drops_status(client):
    order = Order.objects.create(reference="ORD-1", status="shipped")

    response = client.get(f"/api/v2/orders/{order.pk}/")

    assert response.status_code == 200
    assert response.data == {"id": order.pk, "reference": "ORD-1"}


def test_v2_order_schema_drops_status(client):
    properties = _schema_properties(client, "v2", "OrderSerializerV2")

    assert set(properties) == {"id", "reference"}


# --- row 9: flat -> nested restructuring (payments: card_last4/card_brand) ------


@pytest.mark.django_db
def test_v1_payment_response_keeps_flat_card_fields(client):
    payment = Payment.objects.create(amount=1050, currency="USD", card_last4="4242", card_brand="visa")

    response = client.get(f"/api/v1/payments/{payment.pk}/")

    assert response.status_code == 200
    assert response.data["card_last4"] == "4242"
    assert response.data["card_brand"] == "visa"
    assert "card" not in response.data


@pytest.mark.django_db
def test_v2_payment_response_nests_card_fields(client):
    payment = Payment.objects.create(amount=1050, currency="USD", card_last4="4242", card_brand="visa")

    response = client.get(f"/api/v2/payments/{payment.pk}/")

    assert response.status_code == 200
    assert response.data["card"] == {"last4": "4242", "brand": "visa"}
    assert "card_last4" not in response.data
    assert "card_brand" not in response.data


@pytest.mark.django_db
def test_v2_payment_create_accepts_nested_card(client):
    from django.contrib.auth.models import User

    client.force_authenticate(user=User.objects.create(username="staff"))

    response = client.post(
        "/api/v2/payments/",
        {"amount": 500, "currency": "USD", "card": {"last4": "1111", "brand": "mastercard"}},
        format="json",
    )

    assert response.status_code == 201
    payment = Payment.objects.get(pk=response.data["id"])
    assert payment.card_last4 == "1111"
    assert payment.card_brand == "mastercard"


def test_v2_payment_schema_has_nested_card_not_flat_fields(client):
    properties = _schema_properties(client, "v2", "PaymentSerializerV2")

    assert "card" in properties
    assert "card_last4" not in properties
    assert "card_brand" not in properties


# --- row 10: SerializerMethodField output change (payments: display_amount) -----


@pytest.mark.django_db
def test_v1_display_amount_keeps_its_original_format(client):
    payment = Payment.objects.create(amount=1050, currency="USD")

    response = client.get(f"/api/v1/payments/{payment.pk}/")

    assert response.data["display_amount"] == "10.50 USD"


@pytest.mark.django_db
def test_v2_display_amount_format_changes(client):
    payment = Payment.objects.create(amount=1050, currency="USD")

    response = client.get(f"/api/v2/payments/{payment.pk}/")

    assert response.data["display_amount"] == "$10.50"


def test_display_amount_schema_is_identical_across_versions_despite_the_format_change(client):
    """The diff-blind half of row 10: two versions producing genuinely different
    bytes on the wire, with a byte-identical schema property either side — the
    only way to have caught the behavior change above was to call the endpoint."""
    v1_properties = _schema_properties(client, "v1", "Payment")
    v2_properties = _schema_properties(client, "v2", "PaymentSerializerV2")

    assert v1_properties["display_amount"] == v2_properties["display_amount"]


# --- row 14b: @action removal (payments: refund) --------------------------------


@pytest.mark.django_db
def test_v1_refund_action_still_serves(client):
    from django.contrib.auth.models import User

    client.force_authenticate(user=User.objects.create(username="staff"))
    payment = Payment.objects.create(amount=500, currency="USD", status="completed")

    response = client.post(f"/api/v1/payments/{payment.pk}/refund/")

    assert response.status_code == 200


@pytest.mark.django_db
def test_v2_refund_action_is_gone(client):
    from django.contrib.auth.models import User

    client.force_authenticate(user=User.objects.create(username="staff"))
    payment = Payment.objects.create(amount=500, currency="USD", status="completed")

    response = client.post(f"/api/v2/payments/{payment.pk}/refund/")

    assert response.status_code == 404


def test_v2_schema_has_no_refund_path(client):
    v1_paths = _schema_paths(client, "v1")
    v2_paths = _schema_paths(client, "v2")

    assert "/api/v1/payments/{id}/refund/" in v1_paths
    assert "/api/v2/payments/{id}/refund/" not in v2_paths


# --- row 12: whole-resource removal (legacy-invoices) ---------------------------


@pytest.mark.django_db
def test_v1_legacy_invoices_still_serves(client):
    LegacyInvoice.objects.create(number="INV-1", amount=999)

    response = client.get("/api/v1/legacy-invoices/")

    assert response.status_code == 200
    assert response.data["results"][0]["number"] == "INV-1"


@pytest.mark.django_db
def test_v2_legacy_invoices_does_not_exist(client):
    LegacyInvoice.objects.create(number="INV-1", amount=999)

    response = client.get("/api/v2/legacy-invoices/")

    assert response.status_code == 404


def test_v2_schema_has_no_legacy_invoices_path(client):
    v1_paths = _schema_paths(client, "v1")
    v2_paths = _schema_paths(client, "v2")

    assert "/api/v1/legacy-invoices/" in v1_paths
    assert not any("legacy-invoices" in path for path in v2_paths)


# --- row 13: URL prefix change (webhooks: two segments deep -> flat) ------------


@pytest.mark.django_db
def test_v1_webhooks_still_mounted_two_segments_deep(client):
    webhook = WebhookEndpoint.objects.create(
        target_url="https://example.com/hook", event_type="order.created", secret="s3cr3t"
    )

    old_path = client.get(f"/api/v1/integrations/webhooks/{webhook.pk}/")
    moved_path = client.get(f"/api/v1/webhooks/{webhook.pk}/")

    assert old_path.status_code == 200
    assert moved_path.status_code == 404


@pytest.mark.django_db
def test_v2_webhooks_mounted_at_the_shorter_prefix(client):
    webhook = WebhookEndpoint.objects.create(
        target_url="https://example.com/hook", event_type="order.created", secret="s3cr3t"
    )

    moved_path = client.get(f"/api/v2/webhooks/{webhook.pk}/")
    old_path = client.get(f"/api/v2/integrations/webhooks/{webhook.pk}/")

    assert moved_path.status_code == 200
    assert old_path.status_code == 404


def test_v2_schema_reflects_the_new_webhooks_prefix_only(client):
    v1_paths = _schema_paths(client, "v1")
    v2_paths = _schema_paths(client, "v2")

    assert "/api/v1/integrations/webhooks/" in v1_paths
    assert "/api/v2/webhooks/" in v2_paths
    assert "/api/v2/integrations/webhooks/" not in v2_paths


# --- composition: unmodified resources are inherited, not copied ----------------


@pytest.mark.django_db
def test_addresses_is_inherited_unchanged_from_v1_into_v2(client):
    """addresses was never touched by v2's Delta — this proves the resolution
    table composes v1's actual handler through to v2, rather than v2 needing its
    own copy to keep serving it."""
    user = UserProfile.objects.create(username="ada", email="ada@example.com")
    from addresses.models import Address

    Address.objects.create(user=user, line1="1 Infinite Loop", city="Cupertino", postal_code="95014", country="US")

    response = client.get("/api/v2/addresses/")

    assert response.status_code == 200
    assert response.data["results"][0]["user"]["username"] == "ada"


def test_v1_and_v2_schema_documents_do_not_leak_each_others_routes(client):
    v1_paths = _schema_paths(client, "v1")
    v2_paths = _schema_paths(client, "v2")

    assert "/api/v1/legacy-invoices/" not in v2_paths
    assert "/api/v2/webhooks/" not in v1_paths
    assert all(path.startswith("/api/v1/") for path in v1_paths)
    assert all(path.startswith("/api/v2/") for path in v2_paths)


@pytest.mark.parametrize(
    ("docs_path", "expected_schema_path"),
    [
        ("/api/docs/", "/api/schema/"),
        ("/api/v1/docs/", "/api/v1/schema/"),
        ("/api/v2/docs/", "/api/v2/schema/"),
    ],
)
def test_each_docs_page_points_at_its_own_schema_not_a_sibling_versions(client, docs_path, expected_schema_path):
    """Regression: the pre-existing project's own api/docs/ and api/schema/ stay
    mounted unchanged alongside the versioned surface (adoption is additive, not
    a replacement — see config/urls.py), and the Base Version deliberately keeps
    bare, unnamespaced route names (ADR 0001 item 4) to match what the
    pre-existing project already used. Left alone, that means the pre-existing
    "schema"/"docs" names and v1's own collide, and Django's reverse() silently
    resolves the bare name to whichever pattern was registered last — the old
    docs page ends up pointing at v1's schema, not its own. api/v1/registry.py
    renames v1's routes to "v1-schema"/"v1-docs" to keep all three unambiguous.
    """
    response = client.get(docs_path)

    assert response.status_code == 200
    match = re.search(r'url:\s*[\'"]([^\'"]+)[\'"]', response.content.decode())
    assert match is not None
    assert match.group(1) == expected_schema_path
