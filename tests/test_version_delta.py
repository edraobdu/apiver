import pytest

from apiver.drf import Version
from tests.testapp.views import PaymentViewSet, PaymentViewSetV2, PingViewSet, RefundViewSet


def test_override_replaces_the_registration():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")

    v1.override("payments", PaymentViewSetV2, basename="payments")

    route = v1.resolution_table["^payments/(?P<pk>[^/.]+)/$"]
    assert route.registration.handler is PaymentViewSetV2


def test_override_on_a_missing_key_raises():
    v1 = Version("v1")

    with pytest.raises(ValueError):
        v1.override("payments", PaymentViewSetV2, basename="payments")


def test_override_on_an_inherited_key_replaces_it_for_the_child_only():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v2 = v1.derive("v2")

    v2.override("payments", PaymentViewSetV2, basename="payments")

    assert v2.resolution_table["^payments/(?P<pk>[^/.]+)/$"].registration.handler is PaymentViewSetV2
    assert v1.resolution_table["^payments/(?P<pk>[^/.]+)/$"].registration.handler is PaymentViewSet


def test_override_with_fewer_routes_drops_the_parents_extra_paths():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v2 = v1.derive("v2")

    v2.override("payments", PaymentViewSetV2, basename="payments")

    assert "^payments/$" not in v2.resolution_table
    assert "^payments/$" in v1.resolution_table


def test_override_without_a_name_for_a_non_viewset_raises():
    v1 = Version("v1")
    v1.register("pong/", lambda request: None, name="pong")

    with pytest.raises(TypeError):
        v1.override("pong/", lambda request: None)


def test_remove_erases_every_path_the_registration_expanded_into():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")

    v1.remove("payments")

    assert "^payments/$" not in v1.resolution_table
    assert "^payments/(?P<pk>[^/.]+)/$" not in v1.resolution_table


def test_remove_on_an_absent_key_raises():
    v1 = Version("v1")

    with pytest.raises(ValueError):
        v1.remove("payments")


def test_removing_the_same_key_twice_raises():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.remove("payments")

    with pytest.raises(ValueError):
        v1.remove("payments")


def test_remove_on_an_inherited_key_hides_it_from_the_child_only():
    v1 = Version("v1")
    v1.register("ping", PingViewSet, basename="ping")
    v2 = v1.derive("v2")

    v2.remove("ping")

    assert "^ping/$" not in v2.resolution_table
    assert "^ping/$" in v1.resolution_table


def test_removed_key_can_be_registered_again():
    v1 = Version("v1")
    v1.register("ping", PingViewSet, basename="ping")
    v1.remove("ping")

    v1.register("ping", PingViewSet, basename="ping-again")

    assert "^ping/$" in v1.resolution_table


def test_freeze_blocks_register():
    v1 = Version("v1")
    v1.freeze()

    with pytest.raises(RuntimeError):
        v1.register("ping", PingViewSet, basename="ping")


def test_freeze_blocks_override():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.freeze()

    with pytest.raises(RuntimeError):
        v1.override("payments", PaymentViewSetV2, basename="payments")


def test_freeze_blocks_remove():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.freeze()

    with pytest.raises(RuntimeError):
        v1.remove("payments")


def test_freeze_does_not_block_derive():
    v1 = Version("v1")
    v1.freeze()

    v2 = v1.derive("v2")

    v2.register("refunds", RefundViewSet, basename="refunds")
    assert "^refunds/$" in v2.resolution_table


def test_freeze_does_not_affect_an_already_derived_childs_mutability():
    v1 = Version("v1")
    v2 = v1.derive("v2")
    v1.freeze()

    v2.register("refunds", RefundViewSet, basename="refunds")

    assert "^refunds/$" in v2.resolution_table
