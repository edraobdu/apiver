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


def test_schema_endpoint_answers_a_real_request(client):
    response = client.get("/api/v1/schema/")

    assert response.status_code == 200


def test_base_version_schema_contains_exactly_its_own_paths(client):
    doc = _schema(client, "v1")

    assert set(doc["paths"]) == {
        "/api/v1/ping/",
        "/api/v1/payments/",
        "/api/v1/payments/{id}/",
        "/api/v1/payments/summary/",
        "/api/v1/pong/",
    }


def test_derived_version_schema_includes_inherited_and_own_paths(client):
    doc = _schema(client, "v2")

    assert "/api/v2/refunds/" in doc["paths"]
    assert "/api/v2/ping/" in doc["paths"]
    assert "/api/v2/payments/{id}/" in doc["paths"]


def test_sibling_versions_paths_never_leak_into_each_others_schema(client):
    v1_doc = _schema(client, "v1")
    v2_doc = _schema(client, "v2")

    assert "/api/v2/refunds/" not in v1_doc["paths"]
    assert not any(path.startswith("/api/v2/") for path in v1_doc["paths"])
    assert not any(path.startswith("/api/v1/") for path in v2_doc["paths"])


def test_removed_resource_is_absent_from_the_removing_versions_schema(client):
    doc = _schema(client, "v3")

    assert "/api/v3/ping/" not in doc["paths"]


def test_overridden_resources_dropped_route_leaves_no_stale_path(client):
    """PaymentViewSetV2 has no list action, so V3's schema must not carry
    the parent's now-stale list path (ADR 0001 item 3)."""
    doc = _schema(client, "v3")

    assert "/api/v3/payments/" not in doc["paths"]
    assert "/api/v3/payments/{id}/" in doc["paths"]


def test_no_duplicate_operation_ids_within_a_document(client):
    for version in ("v1", "v2", "v3"):
        doc = _schema(client, version)
        operation_ids = [
            operation["operationId"] for methods in doc["paths"].values() for operation in methods.values()
        ]
        assert len(operation_ids) == len(set(operation_ids))


def test_overridden_resource_gets_its_own_component_not_the_parents(client):
    v1_doc = _schema(client, "v1")
    v3_doc = _schema(client, "v3")

    assert "Payment" in v1_doc["components"]["schemas"]
    assert "PaymentV2" in v3_doc["components"]["schemas"]
    assert v1_doc["components"]["schemas"]["Payment"] != v3_doc["components"]["schemas"]["PaymentV2"]


def test_schema_path_prefix_is_pinned_so_operation_ids_dont_drift(client):
    """A pinned SCHEMA_PATH_PREFIX means operationIds are a function of the
    route only, not of which other routes happen to share the document
    (ADR 0002 item 9) — adding refunds to V2 must not rename V1's payments
    operationId."""
    v1_doc = _schema(client, "v1")
    v2_doc = _schema(client, "v2")

    v1_op = v1_doc["paths"]["/api/v1/payments/{id}/"]["get"]["operationId"]
    v2_op = v2_doc["paths"]["/api/v2/payments/{id}/"]["get"]["operationId"]
    assert v1_op == "payments_retrieve"
    assert v2_op == "payments_retrieve"
