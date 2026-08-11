"""Pins the undocumented DRF internals apiver's composition depends on
(ticket 21, ADR 0001 Consequences, ADR 0005).

`callback.cls`, `callback.initkwargs` and `callback.actions` appear nowhere
in DRF's documentation — apiver's `_route_identity()` (`version.py`) reads
them anyway, on the same footing as DRF's own browsable API, schema
generator, drf-spectacular and drf-yasg. Treated as de-facto stable, not
contractual: this module is what turns a silent upstream break into a loud
one, inside apiver's own suite, at the exact seam apiver relies on rather
than by re-deriving each attribute from scratch. It exercises the pinned
range in `pyproject.toml`; a wider matrix (multiple Python/Django/DRF/
drf-spectacular combinations within that range) is CI's job, not this
module's — these assertions just need to run under each leg.
"""

import inspect

from rest_framework.relations import HyperlinkedRelatedField
from rest_framework.routers import DefaultRouter, SimpleRouter
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet


class _PingViewSet(ViewSet):
    def list(self, request):
        raise NotImplementedError


class _PingView(APIView):
    def get(self, request):
        raise NotImplementedError


def test_viewset_as_view_callback_carries_cls_initkwargs_and_actions():
    # version.py's _route_identity() reads exactly these three off a
    # ViewSet's built callback — none of it documented DRF API.
    callback = _PingViewSet.as_view({"get": "list"}, basename="ping")

    assert callback.cls is _PingViewSet
    assert callback.initkwargs == {"basename": "ping"}
    assert callback.actions == {"get": "list"}


def test_apiview_as_view_callback_carries_cls_and_initkwargs_but_no_actions():
    # _route_identity() falls back to `callback.cls` for non-ViewSet
    # handlers when `.actions` is absent (version.py:113).
    callback = _PingView.as_view()

    assert callback.cls is _PingView
    assert callback.initkwargs == {}
    assert not hasattr(callback, "actions")


def test_viewset_as_view_resets_basename_detail_and_suffix_on_the_class():
    # ADR 0001: this reset is *why* RouteIdentity is read from the built
    # callback's initkwargs rather than introspected off the class after
    # the fact — the class-level attributes are stale by the next call.
    _PingViewSet.as_view({"get": "list"}, basename="first")
    assert _PingViewSet.basename is None
    assert _PingViewSet.detail is None
    assert _PingViewSet.suffix is None

    _PingViewSet.as_view({"get": "list"}, basename="second")
    assert _PingViewSet.basename is None


def test_empty_simple_router_emits_no_patterns():
    # `Version._build_own()` relies on this to make an empty registration
    # set compose to nothing, not to DefaultRouter's API-root/format-suffix
    # extras (version.py:375).
    assert SimpleRouter().urls == []


def test_empty_default_router_emits_exactly_the_api_root_and_format_suffix_patterns():
    assert len(DefaultRouter().urls) == 2


def test_hyperlinked_related_field_get_url_signature_is_stable():
    # ADR 0005: intra-version hyperlinking rests entirely on this method
    # staying where it is and taking these four positional parameters.
    signature = inspect.signature(HyperlinkedRelatedField.get_url)
    assert list(signature.parameters) == ["self", "obj", "view_name", "request", "format"]
