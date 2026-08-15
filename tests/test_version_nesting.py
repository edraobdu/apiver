import pytest

from apiver.drf import Version
from tests.testapp.views import PaymentsSummaryView, PaymentViewSet, RefundViewSetV2


def test_register_nested_composes_the_parent_prefix_and_lookup_regex():
    v1 = Version("v1")
    v1.register("categories", PaymentViewSet, basename="categories")
    v1.register_nested("products", PaymentViewSet, parent="categories", lookup="<int:category_pk>")

    table = v1.resolution_table

    assert "^categories/(?P<category_pk>[0-9]+)/products/$" in table
    assert "^categories/(?P<category_pk>[0-9]+)/products/(?P<pk>[^/.]+)/$" in table


def test_register_nested_defaults_basename_to_the_leaf_key():
    v1 = Version("v1")
    v1.register("categories", PaymentViewSet, basename="categories")
    v1.register_nested("products", PaymentViewSet, parent="categories", lookup="<int:category_pk>")

    route = v1.resolution_table["^categories/(?P<category_pk>[0-9]+)/products/$"]

    assert route.identity.basename == "products"
    assert route.registration.key == "categories/(?P<category_pk>[0-9]+)/products"


def test_register_nested_chains_three_levels_deep():
    v1 = Version("v1")
    v1.register("categories", PaymentViewSet, basename="categories")
    v1.register_nested("products", PaymentViewSet, parent="categories", lookup="<int:category_pk>")
    v1.register_nested("reviews", PaymentViewSet, parent="products", lookup="<int:product_pk>")

    table = v1.resolution_table

    assert "^categories/(?P<category_pk>[0-9]+)/products/(?P<product_pk>[0-9]+)/reviews/$" in table


def test_register_nested_supports_two_siblings_under_one_parent():
    v1 = Version("v1")
    v1.register("categories", PaymentViewSet, basename="categories")
    v1.register_nested("products", PaymentViewSet, parent="categories", lookup="<int:category_pk>")
    v1.register_nested("collections", PaymentViewSet, parent="categories", lookup="<int:category_pk>")

    table = v1.resolution_table

    assert "^categories/(?P<category_pk>[0-9]+)/products/$" in table
    assert "^categories/(?P<category_pk>[0-9]+)/collections/$" in table


def test_register_nested_raises_if_parent_is_not_registered():
    v1 = Version("v1")

    with pytest.raises(ValueError):
        v1.register_nested("products", PaymentViewSet, parent="categories", lookup="<int:category_pk>")


def test_register_nested_raises_if_parent_is_not_a_viewset():
    v1 = Version("v1")
    v1.register("summary/", PaymentsSummaryView, name="payments-summary")

    with pytest.raises(TypeError):
        v1.register_nested("products", PaymentViewSet, parent="summary/", lookup="<int:category_pk>")


def test_override_nested_replaces_the_same_compound_key():
    v1 = Version("v1")
    v1.register("categories", PaymentViewSet, basename="categories")
    v1.register_nested("products", PaymentViewSet, parent="categories", lookup="<int:category_pk>")
    v1.freeze()

    v2 = v1.derive("v2")
    v2.override_nested("products", RefundViewSetV2, parent="categories", lookup="<int:category_pk>")

    table = v2.resolution_table
    route = table["^categories/(?P<category_pk>[0-9]+)/products/$"]

    assert route.registration.handler is RefundViewSetV2
    assert route.registration.key == "categories/(?P<category_pk>[0-9]+)/products"


def test_override_nested_touches_only_the_overridden_leaf():
    v1 = Version("v1")
    v1.register("categories", PaymentViewSet, basename="categories")
    v1.register_nested("products", PaymentViewSet, parent="categories", lookup="<int:category_pk>")
    v1.register_nested("collections", PaymentViewSet, parent="categories", lookup="<int:category_pk>")
    v1.freeze()

    v2 = v1.derive("v2")
    v2.override_nested("products", RefundViewSetV2, parent="categories", lookup="<int:category_pk>")

    table = v2.resolution_table

    assert table["^categories/(?P<category_pk>[0-9]+)/products/$"].registration.handler is RefundViewSetV2
    assert table["^categories/(?P<category_pk>[0-9]+)/collections/$"].registration.handler is PaymentViewSet


def test_remove_drops_only_the_nested_leaf_and_keeps_the_parent():
    v1 = Version("v1")
    v1.register("categories", PaymentViewSet, basename="categories")
    v1.register_nested("products", PaymentViewSet, parent="categories", lookup="<int:category_pk>")
    v1.freeze()

    v2 = v1.derive("v2")
    v2.remove("categories/(?P<category_pk>[0-9]+)/products")

    table = v2.resolution_table

    assert "^categories/(?P<category_pk>[0-9]+)/products/$" not in table
    assert "^categories/$" in table
