import pytest
import yaml
from django.urls import reverse
from rest_framework.test import APIClient

from apiver.drf import Alias, Version


@pytest.fixture
def client():
    return APIClient()


def test_alias_is_declared_independently_of_its_target():
    v2 = Version("v2")

    stable = Alias("stable", target=v2)

    assert stable.name == "stable"
    assert stable.target is v2


def test_alias_can_be_repointed_by_reassigning_target():
    v1 = Version("v1")
    v2 = v1.derive("v2")
    stable = Alias("stable", target=v1)

    stable.target = v2

    assert stable.target is v2
    _, app_name, _ = stable.urls
    assert app_name == "v2"


def test_alias_gets_its_own_instance_namespace_distinct_from_its_targets_app_name():
    v1 = Version("v1")
    v2 = v1.derive("v2")
    stable = Alias("stable", target=v2)

    _, app_name, namespace = stable.urls

    assert app_name == "v2"
    assert namespace == "stable"


def test_alias_serves_a_route_inherited_through_its_target(client):
    response = client.get("/api/stable/payments/42/")

    assert response.status_code == 200
    assert response.json() == {"id": "42"}


def test_alias_serves_a_route_the_target_registered_itself(client):
    response = client.get("/api/stable/refunds/")

    assert response.status_code == 200
    assert response.json() == {"results": ["r1"]}


def test_alias_reverse_resolves_independently_of_the_targets_own_namespace():
    stable_url = reverse("stable:payments-detail", args=["42"])
    v2_url = reverse("v2:payments-detail", args=["42"])

    assert stable_url == "/api/stable/payments/42/"
    assert v2_url == "/api/v2/payments/42/"
    assert stable_url != v2_url


def test_alias_schema_route_reuses_the_targets_schema_document_verbatim(client):
    """The alias's schema route is the same SpectacularAPIView instance as
    v2's own — not a second document generated for the alias's own prefix
    (ticket 12) — so it still reports v2's own path prefix."""
    stable_doc = yaml.safe_load(client.get("/api/stable/schema/").content)
    v2_doc = yaml.safe_load(client.get("/api/v2/schema/").content)

    assert stable_doc == v2_doc
    assert any(path.startswith("/api/v2/") for path in stable_doc["paths"])
    assert not any(path.startswith("/api/stable/") for path in stable_doc["paths"])
