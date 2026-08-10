import pytest

from apiver.drf import Version
from tests.testapp.views import PaymentViewSet, PingViewSet, RefundViewSet


def test_derive_returns_a_new_version_with_self_as_parent():
    v1 = Version("v1")

    v2 = v1.derive("v2")

    assert v2.name == "v2"
    assert v2.parent is v1


def test_derived_version_with_no_registrations_of_its_own_inherits_parents_table():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.register("ping", PingViewSet, basename="ping")

    v2 = v1.derive("v2")

    assert v2.resolution_table.keys() == v1.resolution_table.keys()


def test_untouched_routes_are_the_same_route_objects_as_the_parents_not_rebuilt_copies():
    """Resolution-table identity seam (ticket 08): a child that doesn't touch
    a route must reuse its parent's actual Route — not an equal-but-rebuilt
    one — because that Route wraps the actual callback object DRF dispatches
    to."""
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    table_v1 = v1.resolution_table

    v2 = v1.derive("v2")
    table_v2 = v2.resolution_table

    for key in table_v1:
        assert table_v2[key] is table_v1[key]


def test_parent_is_unmutated_and_still_reusable_after_a_child_is_composed():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    table_before = v1.resolution_table

    v2 = v1.derive("v2")
    _ = v2.resolution_table

    table_after = v1.resolution_table
    assert table_after.keys() == table_before.keys()
    for key in table_before:
        assert table_after[key] is table_before[key]


def test_registrations_added_to_a_still_mutable_parent_are_visible_to_an_existing_child():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v2 = v1.derive("v2")

    assert "^ping/$" not in v2.resolution_table

    v1.register("ping", PingViewSet, basename="ping")

    assert "^ping/$" in v2.resolution_table


def test_deriving_twice_off_the_same_mutable_parent_gives_independent_branches():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")

    v2a = v1.derive("v2a")
    v2b = v1.derive("v2b")
    v2a.register("ping", PingViewSet, basename="ping")
    v2b.register("refunds", RefundViewSet, basename="refunds")

    assert "^ping/$" in v2a.resolution_table
    assert "^ping/$" not in v2b.resolution_table
    assert "^refunds/$" in v2b.resolution_table
    assert "^refunds/$" not in v2a.resolution_table
    assert "^ping/$" not in v1.resolution_table
    assert "^refunds/$" not in v1.resolution_table


def test_a_child_can_register_a_new_key_the_parent_never_had():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v2 = v1.derive("v2")

    v2.register("refunds", RefundViewSet, basename="refunds")

    assert "^refunds/$" in v2.resolution_table
    assert "^refunds/$" not in v1.resolution_table


def test_registering_a_key_already_used_by_an_ancestor_raises():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v2 = v1.derive("v2")

    with pytest.raises(ValueError):
        v2.register("payments", PaymentViewSet, basename="payments-again")


def test_base_version_urls_have_no_app_name():
    v1 = Version("v1")

    _, app_name = v1.urls

    assert app_name is None


def test_derived_version_urls_are_namespaced_by_its_own_name():
    v1 = Version("v1")
    v2 = v1.derive("v2")

    _, app_name = v2.urls

    assert app_name == "v2"
