"""
Verification suite for wayfinder ticket 05 — "Prove the mechanism".

Each test is numbered against the ticket's own acceptance list, plus two
extra sections (50-endpoint acceptance test; ordering hazard regression).
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from spike.apiver_core import Version
from spike.models import Order, Payment, UserProfile
from spike.v1.registry import v1
from spike.v1.views import OrderViewSet, PaymentViewSet, UserViewSet
from spike.v2.registry import v2
from spike.v2.views import PaymentV2ViewSet


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def seed_data(db):
    user = UserProfile.objects.create(username="ada", email="ada@example.com")
    payment = Payment.objects.create(amount=1500, currency="USD")
    order = Order.objects.create(reference="ORD-1")
    return {"user": user, "payment": payment, "order": order}


# ---------------------------------------------------------------------------
# 1. V1 routes all work and use V1 implementations.
# ---------------------------------------------------------------------------


def test_v1_users_list_works(client, seed_data):
    resp = client.get("/api/v1/users/")
    assert resp.status_code == 200
    assert resp.data[0]["username"] == "ada"


def test_v1_payments_uses_v1_serializer_shape(client, seed_data):
    resp = client.get("/api/v1/payments/")
    assert resp.status_code == 200
    assert resp.data[0]["amount"] == 1500  # plain int — V1 shape, not "1500.00"


def test_v1_orders_list_works(client, seed_data):
    resp = client.get("/api/v1/orders/")
    assert resp.status_code == 200
    assert resp.data[0]["reference"] == "ORD-1"


def test_v1_payments_summary_apiview_works(client, seed_data):
    resp = client.get("/api/v1/payments/summary/")
    assert resp.status_code == 200
    assert resp.data == {"total": 1500, "count": 1}


# ---------------------------------------------------------------------------
# 2. V2 inherits unchanged routes and resolves them to V1 implementations.
# ---------------------------------------------------------------------------


def test_v2_users_inherited_from_v1(client, seed_data):
    resp = client.get("/api/v2/users/")
    assert resp.status_code == 200
    assert resp.data[0]["username"] == "ada"
    # same viewset class, not a V2 reimplementation
    assert v2.resolution_table()["users"].handler is UserViewSet


def test_v2_payments_summary_inherited_from_v1(client, seed_data):
    resp = client.get("/api/v2/payments/summary/")
    assert resp.status_code == 200
    assert resp.data == {"total": 1500, "count": 1}


# ---------------------------------------------------------------------------
# 3. V2 payments uses the V2 serializer (overridden field type).
# ---------------------------------------------------------------------------


def test_v2_payments_uses_v2_serializer_shape(client, seed_data):
    resp = client.get("/api/v2/payments/")
    assert resp.status_code == 200
    # DecimalField renders as a JSON string ("1500.00"), not the int V1 emits (1500).
    assert Decimal(resp.data[0]["amount"]) == Decimal("1500.00")
    assert isinstance(resp.data[0]["amount"], str)
    assert v2.resolution_table()["payments"].handler is PaymentV2ViewSet


# ---------------------------------------------------------------------------
# 4. The removed resource 404s under V2 and still works under V1.
# ---------------------------------------------------------------------------


def test_v2_orders_removed(client, seed_data):
    resp = client.get("/api/v2/orders/")
    assert resp.status_code == 404


def test_v1_orders_still_works_after_v2_removal(client, seed_data):
    resp = client.get("/api/v1/orders/")
    assert resp.status_code == 200
    assert resp.data[0]["reference"] == "ORD-1"


# ---------------------------------------------------------------------------
# 5. Registering V2 does not mutate V1 (the shared-mutable-registry trap).
#    v2.registry is already imported (module-level side effect) by the time
#    this test runs, so this is genuinely "assert V1 after V2 was built".
# ---------------------------------------------------------------------------


def test_v1_registrations_unmutated_by_v2(client, seed_data):
    table = v1.resolution_table()
    assert table["payments"].handler is PaymentViewSet  # not PaymentV2ViewSet
    assert table["orders"].handler is OrderViewSet  # still present in V1
    assert "orders" not in v1._removed  # v2's remove() didn't leak backward

    # And the live route still serves the V1 shape, not V2's.
    resp = client.get("/api/v1/payments/")
    assert resp.data[0]["amount"] == 1500
    assert not isinstance(resp.data[0]["amount"], str)


# ---------------------------------------------------------------------------
# 6. reverse() resolves correctly and unambiguously per version.
# ---------------------------------------------------------------------------


def test_reverse_v1_uses_bare_name(seed_data):
    url = reverse("payments-detail", args=[seed_data["payment"].pk])
    assert url == f"/api/v1/payments/{seed_data['payment'].pk}/"


def test_reverse_v2_uses_namespaced_name(seed_data):
    url = reverse("v2:payments-detail", args=[seed_data["payment"].pk])
    assert url == f"/api/v2/payments/{seed_data['payment'].pk}/"


def test_bare_name_does_not_silently_resolve_to_v2():
    # If namespacing weren't applied, both versions would fight over the same
    # bare "payments-detail" name and reverse() would silently return the last
    # registered one. Confirm the bare name still means V1 even though V2 (built
    # later, at import time) registers a viewset under the same basename.
    assert reverse("payments-detail", args=[1]) == "/api/v1/payments/1/"


# ---------------------------------------------------------------------------
# 7. drf-spectacular generates a complete, collision-free V2 schema.
# ---------------------------------------------------------------------------


def test_v2_schema_is_complete_and_collision_free():
    generator = SchemaGenerator(patterns=v2.urlpatterns())
    schema = generator.get_schema(request=None, public=True)

    paths = schema["paths"]
    # 4 routes: users (list+detail collapse to 1 path each = 2 paths),
    # payments (2 paths), payments/summary (1 path) = 5 path entries,
    # orders is removed so it must not appear anywhere.
    assert not any("orders" in p for p in paths)
    assert any(p.endswith("/summary/") for p in paths)
    assert any(p.rstrip("/").endswith("payments") for p in paths)
    assert any(p.rstrip("/").endswith("users") for p in paths)

    operation_ids = []
    for methods in paths.values():
        for op in methods.values():
            if isinstance(op, dict) and "operationId" in op:
                operation_ids.append(op["operationId"])
    assert len(operation_ids) == len(set(operation_ids)), "duplicate operationId"

    component_names = list(schema.get("components", {}).get("schemas", {}).keys())
    assert len(component_names) == len(set(component_names)), "duplicate component name"
    # version-suffixed class name is load-bearing (ticket 03) — Payment's V2
    # component must not collide with a same-named-but-different V1 component.
    assert "PaymentV2" in component_names
    assert "PaymentV1" not in component_names  # V1 never mounted in this schema


def test_v1_and_v2_schemas_do_not_collide_when_combined():
    """Simulates what a combined document would face: same class name reused
    across versions is safe (identical class), but the two Payment serializers
    are version-suffixed so they never collide even though both derive from
    the same lineage."""
    gen_v1 = SchemaGenerator(patterns=v1.urlpatterns())
    gen_v2 = SchemaGenerator(patterns=v2.urlpatterns())
    schema_v1 = gen_v1.get_schema(request=None, public=True)
    schema_v2 = gen_v2.get_schema(request=None, public=True)

    names_v1 = set(schema_v1.get("components", {}).get("schemas", {}).keys())
    names_v2 = set(schema_v2.get("components", {}).get("schemas", {}).keys())
    shared = names_v1 & names_v2
    # Only the untouched serializers (User, Order-in-v1-only) may be shared —
    # they're the literal same class reused, not a name collision between
    # different classes. Payment must differ.
    assert "PaymentV1" not in names_v2
    assert "PaymentV2" not in names_v1
    for name in shared:
        assert name != "Payment"  # unsuffixed collision would be the trap


# ---------------------------------------------------------------------------
# Ordering hazard: payments/summary/ must not be swallowed by the router's
# generic detail regex (^payments/(?P<pk>[^/.]+)/$ matches "summary" as a pk).
# ---------------------------------------------------------------------------


def test_summary_route_not_swallowed_by_detail_route(client, seed_data):
    resp = client.get("/api/v1/payments/summary/")
    assert resp.status_code == 200
    assert "total" in resp.data  # would be a 404-from-get_object() if swallowed


# ---------------------------------------------------------------------------
# 50-endpoint acceptance test: does the "V2 file" really stay two statements?
# ---------------------------------------------------------------------------


class _DummyViewV1:
    @classmethod
    def as_view(cls):
        def _view(request):
            return None

        return _view


class _DummyViewV2(_DummyViewV1):
    pass


def test_fifty_endpoints_only_two_change_in_v2():
    big_v1 = Version("big-v1")
    for i in range(50):
        big_v1.register_view(f"resource_{i}", _DummyViewV1, url_path=f"resource_{i}/", name=f"resource_{i}")

    # The entire "V2 file": two statements touching 2 of 50 resources.
    big_v2 = Version("big-v2", parent=big_v1)
    big_v2.register_view("resource_0", _DummyViewV2, url_path="resource_0/", name="resource_0")
    big_v2.remove("resource_1")

    table_v1 = big_v1.resolution_table()
    table_v2 = big_v2.resolution_table()

    assert len(table_v1) == 50
    assert len(table_v2) == 49  # 50 - 1 removed

    # The overridden one changed...
    assert table_v2["resource_0"].handler is _DummyViewV2
    # ...and every other surviving resource is the *same object*, proving
    # inheritance rather than 48 lines of re-registration.
    untouched_keys = [k for k in table_v2 if k not in ("resource_0",)]
    assert len(untouched_keys) == 48
    for key in untouched_keys:
        assert table_v2[key] is table_v1[key]

    assert len(big_v2.urlpatterns()) == 49
