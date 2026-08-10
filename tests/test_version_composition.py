import pytest
from rest_framework.routers import SimpleRouter

from apiver.drf import CompositionError, Version
from tests.testapp.views import PaymentViewSet, PingViewSet


def test_duplicate_key_registration_raises():
    v1 = Version("v1")
    v1.register("ping", PingViewSet, basename="ping")

    with pytest.raises(ValueError):
        v1.register("ping", PingViewSet, basename="ping-again")


def test_non_viewset_registration_without_name_raises():
    v1 = Version("v1")

    with pytest.raises(TypeError):
        v1.register("pong/", lambda request: None)


def test_router_instance_is_refused():
    v1 = Version("v1")

    with pytest.raises(TypeError):
        v1.register("payments", SimpleRouter())


def test_router_class_is_refused():
    v1 = Version("v1")

    with pytest.raises(TypeError):
        v1.register("payments", SimpleRouter)


def test_resolution_table_carries_route_identity_for_a_viewset_list_route():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")

    route = v1.resolution_table["^payments/$"]

    assert route.identity.basename == "payments"
    assert route.identity.detail is False
    assert route.identity.action == {"get": "list"}
    assert route.identity.methods == frozenset({"GET"})
    assert route.registration.key == "payments"


def test_resolution_table_carries_route_identity_for_a_viewset_detail_route():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")

    route = v1.resolution_table["^payments/(?P<pk>[^/.]+)/$"]

    assert route.identity.basename == "payments"
    assert route.identity.detail is True
    assert route.identity.action == {"get": "retrieve"}
    assert route.identity.url_name == "payments-detail"
    assert route.registration.key == "payments"


def test_every_resolved_path_traces_back_to_exactly_one_registration():
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")
    v1.register("ping", PingViewSet, basename="ping")

    table = v1.resolution_table

    assert {route.registration.key for route in table.values()} == {"payments", "ping"}


def test_composition_self_verification_catches_an_unaccounted_pattern(monkeypatch):
    """Regression for ADR 0001 item 5: the self-verifying re-walk must hard-fail
    if the router ever produces a pattern with no corresponding Registration —
    exactly what DefaultRouter's api-root view would do."""
    v1 = Version("v1")
    v1.register("payments", PaymentViewSet, basename="payments")

    original_get_urls = SimpleRouter.get_urls

    def rogue_get_urls(self):
        from django.urls import path
        from rest_framework.views import APIView

        class RogueView(APIView):
            def get(self, request):
                return None

        return original_get_urls(self) + [path("rogue/", RogueView.as_view(), name="rogue")]

    monkeypatch.setattr(SimpleRouter, "get_urls", rogue_get_urls)

    with pytest.raises(CompositionError):
        _ = v1.urls
