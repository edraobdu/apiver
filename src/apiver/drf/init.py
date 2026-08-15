"""`apiver init`: walk the live URLconf and generate the base version's
`registry.py`, mounting it into the Aggregation Root (ticket 17, ADR 0003
items 3-4, 7; ticket 43, ADR 0007; ticket #51 — renamed from `migrate`,
since it's the first command every project runs, adopted or greenfield).
`apiver mount` (`write_mount`) shares this module: it generates every later
version's `registry.py` from scratch — `<version> =
<from_version>.derive(<version>)`, with its own schema and docs routes
always wired — then appends its `include()` to that same Aggregation Root
(ticket #47). A developer never hand-writes a version into existence;
`mount` is what creates it, and everything past that (its actual changed
endpoints) is a hand-edit to the file `mount` just created. `apiver alias`
(`write_alias`) also shares this module: it declares a new `Alias` pointing
at an already-mounted Version straight in the Aggregation Root — its
conventional home — with no separate `registry.py` of its own (ticket #53,
ADR 0007's second amendment).

Generates wiring only — it never moves a file. The existing
`serializers.py`/`views.py` stay wherever the pre-existing project already
put them; `registry.py` just imports from there and calls `register()`
(ADR 0003 item 3).

A project with no pre-existing routes under `--prefix` at all — a
greenfield project running `init` for the first time, never having adopted
anything — still gets a valid Base Version out of `init`: no routes is not
a failure, it just means `discover()` classifies nothing beyond the schema
and docs routes `init` always wires unconditionally, the same way `mount`
already wires them for every later version (ticket #51).

This module writes its own URLconf enumerator rather than reusing
drf-spectacular's or DRF's own schema `EndpointEnumerator`. Both are lossy
*schema* filters: `should_include_endpoint` drops every callback without a
`.cls` subclassing `APIView` — every plain Django view, every
`django.views.generic` view, every undecorated function view
(`rest_framework/schemas/generators.py:26-33, 117-118`, ticket 02's
research) — which is exactly the population init must not lose. Ground
truth for a router-registered viewset's `basename`/`detail`/`actions` is
read from `callback.initkwargs`/`callback.actions`, never from the handler
class: `ViewSetMixin.as_view()` resets `cls.basename`/`cls.detail`/
`cls.suffix` to `None` on every call (ticket 02 §3.2, F10), so the class is
stale the moment a second registration happens anywhere in the process.

The 16 failure modes catalogued in ticket 02's research
(`.scratch/apiver-mvp/research/02-urlconf-walk.md` §5) are the checklist
for what this module must refuse rather than silently mis-emit. Discovery
is followed by verification: every generated registration is rebuilt as a
real in-memory `Version` and diffed against what was actually discovered,
so a bug in prefix derivation fails the `init` run instead of shipping a
registry that silently serves the wrong routes (recommendation #5).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from django.conf import settings
from django.urls import URLPattern, URLResolver
from django.urls.resolvers import LocalePrefixPattern, RegexPattern
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import APIRootView

from ..schemes import DEFAULT_SCHEME_NAME, Scheme, UnknownSchemeError, get_scheme
from .manifest import resolve_root_dir
from .version import Version

_FORMAT_SUFFIX_RE = re.compile(r"\(\?P<format>|drf_format_suffix")
_MAX_DEPTH = 64


class InitError(RuntimeError):
    """One or more routes under `--prefix` could not be classified or
    regenerated. Raised with every offending route listed at once —
    init fails closed and writes nothing rather than emit a registry
    that silently drops routes (ticket 02 recommendation #5)."""


def _configured_scheme() -> Scheme:
    """The project's `APIVER_VERSION_SCHEME`-named Scheme (ticket #67, ADR
    0008 item 5) — unset defaults to `sequential`, mirroring
    `manifest._configured_scheme`'s settings-resolution shape but raising
    this module's own `InitError` instead of `ManifestError`."""
    scheme_name = getattr(settings, "APIVER_VERSION_SCHEME", DEFAULT_SCHEME_NAME)
    try:
        return get_scheme(scheme_name)
    except UnknownSchemeError as exc:
        raise InitError(str(exc)) from exc


def _validate_scheme_conformance(name: str, *, scheme: Scheme, arg_prefix: str = "") -> str:
    """`name`, formatted into its Display Name by `scheme` — also the
    strict, CLI-time validation ADR 0008 item 5 requires: `Scheme.format()`
    raises `ValueError` for a non-conforming slug, translated here into the
    existing `InitError` pattern before any scaffold file is written.
    `arg_prefix` mirrors the `--from `-prefixed identifier-check messages
    this module already raises for the same argument.
    """
    try:
        return scheme.format(name)
    except ValueError as exc:
        raise InitError(
            f"{arg_prefix}{name!r} does not conform to the configured "
            f"APIVER_VERSION_SCHEME={scheme.name!r}: {exc}"
        ) from exc


@dataclass(frozen=True)
class _Endpoint:
    """One discovered, in-scope route, before grouping into registrations."""

    path: str  # absolute path, anchors stripped, relative to nothing
    ancestor_prefix: str  # everything before this leaf's own declared text
    url_name: str | None
    callback: Any
    cls: type | None
    actions: dict[str, str] | None
    initkwargs: dict[str, Any]
    is_regex_declared: bool  # re_path(), not path() — checked in discover()
    matched_prefix: str  # which of discover()'s (non-overlapping) --prefix values this fell under


@dataclass(frozen=True)
class RegistrationPlan:
    """One `register()` call init will emit."""

    key: str
    kind: str  # "viewset" | "view" | "schema" | "docs"
    module: str
    symbol: str
    basename: str | None = None
    name: str | None = None
    # Set only for kind == "schema" — the absolute mount prefix passed to
    # `schema_view(prefix=...)` (ADR 0007 item 6). `module`/`symbol` are
    # unused for this kind: there is nothing to import, the handler is
    # `{var_name}.schema_view(prefix=...)` itself.
    schema_prefix: str | None = None


@dataclass
class DiscoveryResult:
    plans: list[RegistrationPlan]
    diagnostics: list[str] = field(default_factory=list)
    _groups: dict[str, list[_Endpoint]] = field(default_factory=dict)


def _strip_anchors(text: str) -> str:
    # `^`/`$` are the only regex metacharacters that survive into a
    # RegexPattern's *declared* text for router-produced leaves — DRF's
    # routes are always `^{prefix}...{trailing_slash}$`, anchored only at
    # position 0/-1 of that text — and `path()`'s RoutePattern text never
    # contains them at all. removeprefix/removesuffix strips exactly that
    # real anchor; a blind global replace does not, because DRF's default
    # lookup_value_regex is itself the negated character class `[^/.]+` —
    # replacing every `^` corrupts it into `[/.]+` ("only slash or dot")
    # the moment a nested router's prefix embeds a parent lookup group.
    return text.removeprefix("^").removesuffix("$")


def _overlaps(a: str, b: str) -> bool:
    return a.startswith(b) or b.startswith(a)


def _walk(
    patterns: Any,
    *,
    prefixes: list[str],
    ancestor_prefix: str,
    depth: int,
    endpoints: list[_Endpoint],
    diagnostics: list[str],
) -> None:
    if depth > _MAX_DEPTH:
        diagnostics.append(
            f"recursion depth exceeded while walking below {ancestor_prefix!r} — a URLconf that "
            "includes itself?"
        )
        return

    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            child_prefix = ancestor_prefix + str(pattern.pattern)
            if not any(_overlaps(_strip_anchors(child_prefix), prefix) for prefix in prefixes):
                continue  # provably outside every --prefix; do not even walk in

            if isinstance(pattern.pattern, LocalePrefixPattern):
                diagnostics.append(
                    "i18n_patterns() found at the URLconf root — its prefix depends on the active "
                    "language at walk time, so the discovered paths would be non-deterministic "
                    "(ticket 02 F14). Not supported by init; adopt without i18n_patterns() first, "
                    "or write registry.py by hand."
                )
                continue
            if pattern.namespace is not None:
                diagnostics.append(
                    f"{child_prefix!r} is included under namespace {pattern.namespace!r} — init "
                    "only supports the base version's bare, unnamespaced URL names (ADR 0001 item 4, "
                    "ticket 02 F15). Remove the namespace before adopting, or write registry.py by "
                    "hand."
                )
                continue

            _walk(
                pattern.url_patterns,
                prefixes=prefixes,
                ancestor_prefix=child_prefix,
                depth=depth + 1,
                endpoints=endpoints,
                diagnostics=diagnostics,
            )
        elif isinstance(pattern, URLPattern):
            declared = str(pattern.pattern)
            # Strip the leaf's own anchors before concatenating, not after:
            # `ancestor_prefix + declared` puts `declared`'s leading `^`
            # mid-string, past where removeprefix("^") would find it.
            absolute = ancestor_prefix + _strip_anchors(declared)
            matched_prefix = next((prefix for prefix in prefixes if absolute.startswith(prefix)), None)
            if matched_prefix is None:
                continue
            if _FORMAT_SUFFIX_RE.search(declared):
                continue  # ticket 02 F16: DefaultRouter's format-suffix duplicate

            callback = pattern.callback
            cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
            if cls is APIRootView:
                continue  # ticket 02 F4: router-computed, nothing to regenerate

            endpoints.append(
                _Endpoint(
                    path=absolute,
                    ancestor_prefix=_strip_anchors(ancestor_prefix),
                    url_name=pattern.name,
                    callback=callback,
                    cls=cls,
                    actions=getattr(callback, "actions", None),
                    initkwargs=getattr(callback, "initkwargs", {}),
                    is_regex_declared=isinstance(pattern.pattern, RegexPattern),
                    matched_prefix=matched_prefix,
                )
            )


def _relative(prefix: str, path: str) -> str:
    return path[len(prefix) :]


def _resolve_class_symbol(
    cls: type, callback: Any, route_path: str, diagnostics: list[str]
) -> tuple[str, str] | None:
    """Resolve an importable `(module, name)` for a class-based handler,
    identity-checked against the live object apiver discovered.

    Two identities are accepted, because `@api_view` breaks the obvious
    one: for an ordinary class the module-level name must resolve back to
    `cls` itself; for `@api_view`, `cls` is a synthetic
    `type('WrappedAPIView', (APIView,), ...)` whose `__qualname__` is
    always the useless literal `'WrappedAPIView'` while only `__name__` is
    rewritten to the decorated function's name (ticket 02 F2) — the name
    that resolves in the module is the *callback* (the view function
    `@api_view` produced), not the class.
    """
    qualname = cls.__qualname__
    if "<locals>" in qualname or qualname == "<lambda>":
        diagnostics.append(
            f"{route_path!r} is served by {cls.__module__}.{qualname}, built inside a function, "
            "closure, or a decorator that doesn't use functools.wraps — there is no import statement "
            "that names it (ticket 02 F1/F3/F5). Register it by hand, or move its definition to "
            "module level."
        )
        return None

    try:
        module = import_module(cls.__module__)
    except ImportError as exc:
        diagnostics.append(f"{route_path!r}: {cls.__module__!r} could not be imported: {exc}")
        return None

    name = cls.__name__
    candidate = getattr(module, name, None)
    if candidate is cls or candidate is callback:
        return cls.__module__, name

    diagnostics.append(
        f"{route_path!r} is served by {cls.__module__}.{name}, but that name in the module doesn't "
        "resolve back to the same object apiver discovered — likely reassigned to a different name, "
        "or defined inside urls.py itself (ticket 02 F3/F5). Register it by hand."
    )
    return None


def _resolve_function_symbol(
    callback: Any, route_path: str, diagnostics: list[str]
) -> tuple[str, str] | None:
    """Resolve an importable `(module, name)` for a plain function view —
    no `.cls`/`.view_class` at all, so the callback itself is the symbol.
    """
    qualname = getattr(callback, "__qualname__", None)
    module_name = getattr(callback, "__module__", None)
    if not qualname or not module_name or "<locals>" in qualname or qualname == "<lambda>":
        diagnostics.append(
            f"{route_path!r} has no importable symbol — a lambda, a function defined inside another "
            "function, or wrapped by a decorator/functools.partial that drops the attributes apiver "
            "needs (ticket 02 F1/F3/F5). Register it by hand, or move its definition to module level."
        )
        return None

    try:
        module = import_module(module_name)
    except ImportError as exc:
        diagnostics.append(f"{route_path!r}: {module_name!r} could not be imported: {exc}")
        return None

    name = qualname.split(".")[-1]
    if getattr(module, name, None) is not callback:
        diagnostics.append(
            f"{route_path!r} is served by {module_name}.{name}, but that name doesn't resolve back "
            "to the same callable apiver discovered (ticket 02 F3). Register it by hand."
        )
        return None
    return module_name, name


def _group_key(endpoint: _Endpoint) -> str | None:
    return endpoint.initkwargs.get("basename")


def _derive_router_prefix(
    prefix: str, basename: str, endpoints: list[_Endpoint], diagnostics: list[str]
) -> str | None:
    """The router-local prefix, recovered without ever needing the router
    object (ticket 02 §3.2). Preferred source is the list route's own
    absolute path — it carries no lookup group at all. Falling back to the
    detail route means stripping everything from its lookup group onward;
    DRF's lookup regex is always `{prefix}/(?P<pk>...)`, so the boundary is
    the first named group in the path.
    """
    by_name = {e.url_name: e for e in endpoints}
    list_route = by_name.get(f"{basename}-list")
    if list_route is not None:
        return _relative(prefix, list_route.path).rstrip("/")

    detail_route = by_name.get(f"{basename}-detail")
    if detail_route is not None:
        boundary = detail_route.path.find("(?P<")
        if boundary != -1:
            return _relative(prefix, detail_route.path[:boundary]).rstrip("/")

    diagnostics.append(
        f"could not derive a router prefix for basename {basename!r} — it has neither a "
        f"'{basename}-list' nor a '{basename}-detail' route to derive it from. Register it by hand."
    )
    return None


def discover(
    root_patterns: Any, *, prefixes: list[str], schema_mount_prefix: str, base_name: str
) -> DiscoveryResult:
    """Walk `root_patterns` (a URLconf's `urlpatterns` list), classify
    every in-scope route, and turn it into a plan for `Version.register()`.

    `prefixes` (ticket #61) is one or more absolute paths — a scattered
    pre-existing project's routes rarely all live under one ancestor,
    so `--prefix` is multi-valued and every route under any of them is
    unioned into a single discovery pass, keyed relative to whichever
    prefix it matched (`_Endpoint.matched_prefix`). Callers must ensure
    `prefixes` don't overlap each other (`write_init` rejects that before
    calling in) — `_walk` assumes at most one prefix ever matches a given
    absolute path.

    `schema_mount_prefix` is the base version's full absolute mount path
    (`APIVER_ROOT_PREFIX + f"{base_name}/"`) — known at init time since
    ADR 0007 makes it a settings-time fact. It is only ever used to build a
    `schema_view(prefix=...)` plan for a discovered `SpectacularAPIView`
    (ticket #40): the naive `register('schema/', SpectacularAPIView, ...)`
    apiver used to emit is silently wrong the moment a second version
    exists, since that view scans the whole `ROOT_URLCONF` unscoped and
    would start leaking sibling versions' routes.

    `SpectacularSwaggerView`/`SpectacularRedocView` *do* need special-casing,
    despite never scanning the urlconf themselves: both `reverse()` the
    schema route's own `url_name` at request time, and the Base Version
    deliberately keeps bare, unnamespaced route names (ADR 0001 item 4) —
    identical to whatever the pre-existing project already used. Adopting a
    project that keeps its pre-apiver routes mounted alongside the new,
    versioned ones (rather than retiring them) puts two different routes
    behind the exact same name, and Django's `reverse()` for an unqualified
    name silently picks one (ticket 22 finding). `base_name` is used to give
    the discovered schema route a version-qualified name
    (`f"{base_name}-schema"`, always, whether or not the original project
    named it at all) and to point every discovered Swagger/Redoc view's
    `url_name` at that same qualified name, rather than preserving
    whatever bare name they were discovered with.

    Returns diagnostics for anything that could not be classified or
    regenerated rather than raising immediately — every offending route is
    collected and reported together (ticket 02 recommendation #5).

    Always returns at least a schema and a docs plan (ticket #51): if
    nothing under any `prefixes` classified as either, a default is appended —
    `register('schema/', ...)`/`register('docs/', ...)`, the same keys
    `mount` always uses for a freshly-authored version — rather than leaving
    the Base Version to ship without one just because nothing pre-existing
    was there to discover and rename. This is also what makes a genuinely
    route-less project (nothing at all under `prefixes`) still produce a
    valid registry instead of a "nothing discovered" refusal.
    """
    endpoints: list[_Endpoint] = []
    diagnostics: list[str] = []
    _walk(
        root_patterns,
        prefixes=prefixes,
        ancestor_prefix="",
        depth=0,
        endpoints=endpoints,
        diagnostics=diagnostics,
    )

    plans: list[RegistrationPlan] = []
    groups: dict[str, list[_Endpoint]] = {}

    viewset_groups: dict[str, list[_Endpoint]] = {}
    view_endpoints: list[_Endpoint] = []
    for endpoint in endpoints:
        if endpoint.actions is not None:
            basename = _group_key(endpoint)
            if basename is None or endpoint.initkwargs.get("detail") is None:
                diagnostics.append(
                    f"{endpoint.path!r} is served by a ViewSet mounted without basename=/detail= "
                    "passed explicitly — `ViewSetMixin.as_view()` resets the class-level values to "
                    "None on every call, so there is no ground truth to recover them from (ticket 02 "
                    "F10, 'cannot be recovered' #4). Pass them explicitly, or register it by hand."
                )
                continue
            viewset_groups.setdefault(basename, []).append(endpoint)
        else:
            view_endpoints.append(endpoint)

    for basename, group in sorted(viewset_groups.items()):
        cls = group[0].cls
        if cls is None:
            diagnostics.append(f"basename {basename!r} has no recoverable handler class.")
            continue
        matched_prefix = group[0].matched_prefix
        ancestor_relative = _relative(matched_prefix, group[0].ancestor_prefix)
        if "(?P<" in ancestor_relative or "<" in ancestor_relative:
            diagnostics.append(
                f"basename {basename!r} is mounted under a parameterized parent path "
                f"({group[0].ancestor_prefix!r}) — a nested router shape. Nested routers are refused "
                "in 0.1 (ADR 0001 item 5, ticket 02 F7); register it by hand as an explicit path "
                "entry instead."
            )
            continue

        router_prefix = _derive_router_prefix(matched_prefix, basename, group, diagnostics)
        if router_prefix is None:
            continue

        resolved = _resolve_class_symbol(cls, group[0].callback, group[0].path, diagnostics)
        if resolved is None:
            continue
        module, symbol = resolved

        key = router_prefix
        groups[key] = group
        plans.append(
            RegistrationPlan(key=key, kind="viewset", module=module, symbol=symbol, basename=basename)
        )

    docs_view_classes = (SpectacularSwaggerView, SpectacularRedocView)
    schema_endpoints = []
    docs_endpoints = []
    other_endpoints = []
    for endpoint in view_endpoints:
        if endpoint.cls is not None and issubclass(endpoint.cls, SpectacularAPIView):
            schema_endpoints.append(endpoint)
        elif endpoint.cls is not None and issubclass(endpoint.cls, docs_view_classes):
            docs_endpoints.append(endpoint)
        else:
            other_endpoints.append(endpoint)
    view_endpoints = other_endpoints

    # Deterministic regardless of whether (or how) the pre-existing project
    # named its own schema route — every discovered Swagger/Redoc view below
    # points at exactly this name, and nothing else in the generated registry
    # ever collides with it, since a project has only one Base Version.
    # `Version.schema_route_name` is the single source of this convention
    # (ticket 22) — computed off a throwaway Version instance rather than
    # duplicating the string format here.
    schema_name = Version(base_name).schema_route_name

    if len(schema_endpoints) > 1:
        diagnostics.append(
            f"{len(schema_endpoints)} drf-spectacular schema views found under prefixes {prefixes!r} "
            f"({', '.join(sorted(e.path for e in schema_endpoints))}) — init can only auto-wire a "
            "single schema endpoint per version (ticket #40). Remove the extras, or register them by "
            "hand with Version.schema_view(prefix=...)."
        )
    elif schema_endpoints:
        endpoint = schema_endpoints[0]
        if endpoint.cls is not SpectacularAPIView:
            diagnostics.append(
                f"{endpoint.path!r} is served by {endpoint.cls.__module__}.{endpoint.cls.__qualname__}, "
                "a drf-spectacular schema view subclass (e.g. SpectacularYAMLAPIView/"
                "SpectacularJSONAPIView) — init only auto-wires the exact, content-negotiated "
                "SpectacularAPIView (ticket #40). Register it by hand with "
                "Version.schema_view(prefix=...)."
            )
        elif endpoint.is_regex_declared:
            diagnostics.append(
                f"{endpoint.path!r} was declared with re_path(), not path() — apiver's register() "
                "always re-emits explicit views as path() entries, which cannot express an arbitrary "
                "regex (ticket 02 §3.5). Convert it to path() first, or register it by hand."
            )
        else:
            key = _relative(endpoint.matched_prefix, endpoint.path)
            groups[key] = [endpoint]
            plans.append(
                RegistrationPlan(
                    key=key,
                    kind="schema",
                    module="",
                    symbol="",
                    name=schema_name,
                    schema_prefix=schema_mount_prefix,
                )
            )

    for endpoint in sorted(docs_endpoints, key=lambda e: e.path):
        if endpoint.url_name is None:
            diagnostics.append(
                f"{endpoint.path!r} has no url `name=` — register() requires an explicit name= for "
                "non-ViewSet handlers, since there is no router to derive one from (ADR 0002 item 3)."
            )
            continue
        if endpoint.is_regex_declared:
            diagnostics.append(
                f"{endpoint.path!r} was declared with re_path(), not path() — apiver's register() "
                "always re-emits explicit views as path() entries, which cannot express an arbitrary "
                "regex (ticket 02 §3.5). Convert it to path() first, or register it by hand."
            )
            continue

        resolved = _resolve_class_symbol(endpoint.cls, endpoint.callback, endpoint.path, diagnostics)
        if resolved is None:
            continue
        module, symbol = resolved

        key = _relative(endpoint.matched_prefix, endpoint.path)
        # Qualified, not the bare discovered name: the same collision this
        # function's docstring explains for the schema route itself applies
        # here too — reused verbatim, "docs" would collide with the
        # pre-existing project's own same-named route the moment both stay
        # mounted (ticket 22 finding).
        name = f"{base_name}-{endpoint.url_name}"
        groups[key] = [endpoint]
        plans.append(RegistrationPlan(key=key, kind="docs", module=module, symbol=symbol, name=name))

    for endpoint in sorted(view_endpoints, key=lambda e: e.path):
        if endpoint.url_name is None:
            diagnostics.append(
                f"{endpoint.path!r} has no url `name=` — register() requires an explicit name= for "
                "non-ViewSet handlers, since there is no router to derive one from (ADR 0002 item 3)."
            )
            continue
        if endpoint.is_regex_declared:
            diagnostics.append(
                f"{endpoint.path!r} was declared with re_path(), not path() — apiver's register() "
                "always re-emits explicit views as path() entries, which cannot express an arbitrary "
                "regex (ticket 02 §3.5). Convert it to path() first, or register it by hand."
            )
            continue

        key = _relative(endpoint.matched_prefix, endpoint.path)
        if endpoint.cls is not None:
            resolved = _resolve_class_symbol(endpoint.cls, endpoint.callback, endpoint.path, diagnostics)
        else:
            resolved = _resolve_function_symbol(endpoint.callback, endpoint.path, diagnostics)
        if resolved is None:
            continue
        module, symbol = resolved

        groups[key] = [endpoint]
        plans.append(
            RegistrationPlan(key=key, kind="view", module=module, symbol=symbol, name=endpoint.url_name)
        )

    # init wires schema/docs unconditionally — the same guarantee `mount`
    # already gives every later version (ticket #47) — rather than leaving
    # the Base Version to silently ship without either just because nothing
    # pre-existing was discovered to rename (ticket #51). Only added when
    # discovery above didn't already classify one: a pre-existing schema/
    # docs route, once found, keeps its discovered name and prefix exactly
    # as before. Neither default has a discovered `_Endpoint` behind it, so
    # `groups` gets no entry for either key — `verify()` skips the produced-
    # route-count diff for a key it never discovered anything under.
    if not any(plan.kind == "schema" for plan in plans):
        plans.append(
            RegistrationPlan(
                key="schema/",
                kind="schema",
                module="",
                symbol="",
                name=schema_name,
                schema_prefix=schema_mount_prefix,
            )
        )
    if not any(plan.kind == "docs" for plan in plans):
        plans.append(
            RegistrationPlan(
                key="docs/",
                kind="docs",
                module="drf_spectacular.views",
                symbol="SpectacularSwaggerView",
                name=f"{base_name}-docs",
            )
        )

    # A "schema" plan must be emitted last: `schema_view()` snapshots
    # `self.urls` the moment it's called, so it only sees whatever was
    # registered before it — every other registration has to land first for
    # the generated schema to describe the version's complete surface.
    return DiscoveryResult(
        plans=sorted(plans, key=lambda p: (p.kind == "schema", p.key)),
        diagnostics=diagnostics,
        _groups=groups,
    )


def verify(result: DiscoveryResult, *, base_name: str) -> list[str]:
    """Rebuild the plans as a real in-memory `Version` and diff its
    produced routes against what was actually discovered per registration
    (ticket 02 recommendation #5). `Version._build_own()` already
    self-verifies that every registration produces at least one route and
    every produced route traces back to a registration
    (`apiver.drf.version.CompositionError`); this adds the check that
    matters specifically for init — that the *count* of routes produced
    under a derived key matches what was discovered there, catching a
    wrong router-prefix derivation that would otherwise silently register
    the right class under the wrong path.
    """
    version = Version(base_name)
    try:
        for plan in result.plans:
            if plan.kind == "schema":
                handler = version.schema_view(prefix=plan.schema_prefix)
            elif plan.kind == "docs":
                module = import_module(plan.module)
                handler = version.docs_view(view_class=getattr(module, plan.symbol))
            else:
                module = import_module(plan.module)
                handler = getattr(module, plan.symbol)
            if plan.kind == "viewset":
                version.register(plan.key, handler, basename=plan.basename)
            else:
                version.register(plan.key, handler, name=plan.name)
        table = version.resolution_table
    except Exception as exc:  # noqa: BLE001 - any failure here becomes a diagnostic, not a crash
        return [f"generated registry does not compose: {exc}"]

    diagnostics: list[str] = []
    for plan in result.plans:
        if plan.key not in result._groups:
            # init's unconditional default schema/docs plan (no pre-existing
            # route was discovered to diff against) — nothing to verify here
            # beyond what the `try` above already proved: that registering
            # it composes at all.
            continue
        produced = [
            route
            for route in table.values()
            if route.registration is not None and route.registration.key == plan.key
        ]
        expected = len(result._groups.get(plan.key, []))
        if len(produced) != expected:
            diagnostics.append(
                f"verification failed for key {plan.key!r}: discovered {expected} route(s) but "
                f"registering it produced {len(produced)} — init's prefix derivation likely made "
                "a mistake; refusing to write a broken registry.py."
            )
    return diagnostics


def _is_default_docs_view(plan: RegistrationPlan) -> bool:
    """True for a discovered `SpectacularSwaggerView`, unmodified — exactly the
    default `docs_view()` already falls back to, so passing `view_class=`
    explicitly would just repeat what's already true (ticket 22 finding)."""
    return (
        plan.kind == "docs"
        and plan.module == "drf_spectacular.views"
        and plan.symbol == "SpectacularSwaggerView"
    )


def _prefix_segment(key: str) -> str:
    """The text before the first `/` in a registration `key` — the group a
    rendered `register()`/`override()` line belongs under (ticket #105).
    `'orders/(?P<order_pk>[^/.]+)/items'` -> `'orders'`;
    `'addresses'` (no `/` at all) -> `'addresses'`, its own singleton group.
    """
    return key.split("/", 1)[0] or key


def _grouped_register_lines(entries: list[tuple[str, str, bool]]) -> list[str]:
    """`entries` is `(segment, line, headered)` in the order the lines must
    render in — same-segment entries are always already adjacent, since
    both callers sort registrations by key and a shared prefix segment
    keeps consecutive keys together in lexicographic order. Inserts a
    blank line before every new segment; a `# ----- <segment> -----`
    header is only emitted when `headered` is true, so callers can pass
    `headered=False` for `schema/`/`docs/` — they stay singleton and
    unlabeled, at whatever position their own sort already gave them
    (ticket #105).
    """
    lines: list[str] = []
    current_segment: object = object()  # sentinel: always differs from the first entry's segment
    for segment, line, headered in entries:
        if segment != current_segment:
            if lines:
                lines.append("")
            if headered:
                lines.append(f"# ----- {segment} -----")
            current_segment = segment
        lines.append(line)
    return lines


def render_registry(plans: list[RegistrationPlan], *, base_name: str, var_name: str) -> str:
    """Render `registry.py`'s source text. Deterministic: plans are
    processed in the sorted-by-key order `discover()` already returns them
    in, so two runs against the same URLconf produce byte-identical
    output.
    """
    imports: dict[str, list[str]] = {}
    for plan in plans:
        if plan.kind == "schema":
            continue  # no import needed — the handler is {var_name}.schema_view(...)
        if plan.kind == "docs" and _is_default_docs_view(plan):
            continue  # no import needed — SpectacularSwaggerView is docs_view()'s own default
        imports.setdefault(plan.module, []).append(plan.symbol)

    import_lines = [
        f"from {module} import {', '.join(sorted(set(symbols)))}"
        for module, symbols in sorted(imports.items())
    ]

    entries: list[tuple[str, str, bool]] = []
    for plan in plans:
        headered = plan.kind not in ("schema", "docs")
        if plan.kind == "viewset":
            line = f"{var_name}.register({plan.key!r}, {plan.symbol}, basename={plan.basename!r})"
        elif plan.kind == "schema":
            line = (
                f"{var_name}.register({plan.key!r}, {var_name}.schema_view(prefix={plan.schema_prefix!r}), "
                f"name={plan.name!r})"
            )
        elif plan.kind == "docs":
            docs_view_call = (
                f"{var_name}.docs_view()"
                if _is_default_docs_view(plan)
                else f"{var_name}.docs_view(view_class={plan.symbol})"
            )
            line = f"{var_name}.register({plan.key!r}, {docs_view_call}, name={plan.name!r})"
        else:
            line = f"{var_name}.register({plan.key!r}, {plan.symbol}, name={plan.name!r})"
        entries.append((_prefix_segment(plan.key), line, headered))

    register_lines = _grouped_register_lines(entries)

    lines = [
        '"""Generated once by `apiver init`; hand-editable afterwards, like',
        "Django's own `startapp` boilerplate — it is not regenerated on later",
        "runs (ADR 0003 item 4).",
        '"""',
        "",
        "from apiver.drf import Version",
        *([""] + import_lines if import_lines else []),
        "",
        f"{var_name} = Version({base_name!r})",
        *register_lines,
        "",
    ]
    return "\n".join(lines)


def _ensure_root_dir_exists(root_dir: str) -> None:
    """Create `APIVER_ROOT_DIR`'s own package on disk if it isn't importable yet.

    Unlike a version's own subpackage — which a developer authors by hand for
    anything past the Base Version (ADR 0003 item 3) — the root package is
    entirely apiver's own generated territory: nothing else ever has a reason to
    create it first. Without this, the very first `init` or `mount` run in a
    project that has never used apiver before fails on an unhelpful
    `ModuleNotFoundError` for a package the developer was never told to create.

    Warns (non-fatal — the same advisory posture as the manifest-staleness and
    max-live-versions checks) if the target directory already exists on disk at
    this, its first-ever creation — a project's own pre-existing, unrelated
    directory of the same name would otherwise collide silently (ADR 0003's
    ticket #77 amendment, the reason `APIVER_ROOT_DIR` now defaults to
    `"apiversions"` rather than the more collision-prone `"api"`).
    """
    try:
        import_module(root_dir)
        return
    except ImportError:
        pass
    target_dir = Path.cwd().joinpath(*root_dir.split("."))
    if target_dir.exists():
        print(
            f"apiver: {target_dir} already exists and doesn't look like it was created by apiver yet "
            f"— if it collides with a pre-existing project directory, set APIVER_ROOT_DIR to a "
            "different name before continuing (ADR 0003's ticket #77 amendment).",
            file=sys.stderr,
        )
    current = Path.cwd()
    for part in root_dir.split("."):
        current = current / part
        current.mkdir(exist_ok=True)
        init_file = current / "__init__.py"
        if not init_file.is_file():
            init_file.write_text("")


def _resolve_target_dir(module_path: str) -> Path:
    """The filesystem directory `module_path` (e.g. `"api.v1"`) names,
    without requiring the leaf package to exist yet — only its parent must
    be importable. A one-segment `module_path` (no parent package) resolves
    relative to the current working directory.
    """
    parent_path, _, leaf = module_path.rpartition(".")
    if not parent_path:
        return Path.cwd() / module_path
    parent = import_module(parent_path)
    parent_dir = getattr(parent, "__path__", None)
    if parent_dir is None:
        raise InitError(f"{parent_path!r} is a module, not a package — it cannot contain {leaf!r}.")
    return Path(next(iter(parent_dir))) / leaf


def render_aggregation_root(mounts: list[tuple[str, str]], *, root_dir: str) -> str:
    """Render the Aggregation Root's `urls.py` source (ADR 0007 item 2):
    one `include()` per Live Version, each already carrying its full
    absolute mount path. `mounts` is `[(version_name, absolute_prefix),
    ...]`, in the order they should appear.

    Used to render the *initial* file only — by `init` for the base
    version, or by `apiver mount` seeding the very first mount in a
    greenfield project. Every mount after that is appended in place by
    `_write_or_extend_aggregation_root`, never re-rendered from scratch, so
    a developer's hand edits to this file survive.
    """
    import_lines = [f"from {root_dir}.{name}.registry import {name}" for name, _ in mounts]
    mount_lines = [f"    path({prefix!r}, include({name}.urls))," for name, prefix in mounts]
    lines = [
        '"""Generated by `apiver init`; extended in place by `apiver mount`',
        "as later versions are authored (ADR 0007 item 2). Hand-editable in",
        "between — apiver only ever appends a new version's mount here, never",
        'rewrites an existing line."""',
        "",
        "from django.urls import include, path",
        "",
        *import_lines,
        "",
        "urlpatterns = [",
        *mount_lines,
        "]",
        "",
    ]
    return "\n".join(lines)


def _already_mounted(name: str, *, root_dir: str) -> bool:
    """True if `name` is already mounted in the Aggregation Root — either
    as a Version's `include(<name>.urls)` or an Alias's bare `<name>.urls`
    (ticket #53). Both share one prefix namespace under the Aggregation
    Root, so a single check catches a collision either way round.
    """
    aggregation_path = _resolve_target_dir(root_dir) / "urls.py"
    if not aggregation_path.is_file():
        return False
    return re.search(rf"\b{re.escape(name)}\.urls\b", aggregation_path.read_text()) is not None


def _write_or_extend_aggregation_root(version_name: str, *, root_dir: str, mount_prefix: str) -> Path:
    """Mount `version_name` into `<root_dir>/urls.py`, creating the
    Aggregation Root (and its package, if needed) on the very first call —
    shared by `init` (the base version's initial mount, ADR 0007 item 7)
    and `apiver mount` (every authored version after, including as the
    first-ever mount in a greenfield project that never ran init).

    An existing file is extended by text insertion, not regenerated from
    `render_aggregation_root` — the file is meant to be hand-editable
    in between apiver's own appends (ADR 0007 item 2), so a developer's
    edits to earlier entries must survive. Refuses loudly, writing nothing,
    if the file has drifted from the shape apiver itself generates: there
    is no way to safely locate an insertion point in an unrecognized file
    without risking a silently broken urls.py.
    """
    root_dir_path = _resolve_target_dir(root_dir)
    aggregation_path = root_dir_path / "urls.py"

    if not aggregation_path.is_file():
        root_dir_path.mkdir(parents=True, exist_ok=True)
        init_file = root_dir_path / "__init__.py"
        if not init_file.is_file():
            init_file.write_text("")
        aggregation_path.write_text(
            render_aggregation_root([(version_name, mount_prefix)], root_dir=root_dir)
        )
        return aggregation_path

    source = aggregation_path.read_text()
    if re.search(rf"include\({re.escape(version_name)}\.urls\)", source):
        raise InitError(f"{version_name!r} is already mounted in {aggregation_path}.")

    lines = source.splitlines()
    import_indices = [i for i, line in enumerate(lines) if line.startswith(("from ", "import "))]
    if not import_indices:
        raise InitError(
            f"{aggregation_path} has no import statements to extend — has it been hand-edited into "
            "an unrecognized shape?"
        )
    lines.insert(import_indices[-1] + 1, f"from {root_dir}.{version_name}.registry import {version_name}")

    try:
        open_idx = next(i for i, line in enumerate(lines) if line.strip() == "urlpatterns = [")
    except StopIteration:
        raise InitError(
            f"{aggregation_path} has no `urlpatterns = [` list — has it been hand-edited into an "
            "unrecognized shape?"
        ) from None
    try:
        close_idx = next(i for i in range(open_idx + 1, len(lines)) if lines[i].strip() == "]")
    except StopIteration:
        raise InitError(
            f"{aggregation_path}'s urlpatterns list has no closing `]` — has it been hand-edited into "
            "an unrecognized shape?"
        ) from None
    lines.insert(close_idx, f"    path({mount_prefix!r}, include({version_name}.urls)),")

    aggregation_path.write_text("\n".join(lines) + "\n")
    return aggregation_path


def _ensure_package(target_dir: Path) -> None:
    """Create `target_dir` and its `__init__.py` if either is missing —
    the same "make the directory this file is about to land in" step
    `write_init` already does for the base version, shared here so
    `write_mount` doesn't duplicate it for an authored version's package.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    init_file = target_dir / "__init__.py"
    if not init_file.is_file():
        init_file.write_text("")


def render_mount_registry(
    version_name: str, from_version: str, *, root_dir: str, mount_prefix: str, resolved_keys: set[str]
) -> str:
    """Render a freshly-authored version's whole `registry.py` (ticket
    #47): derive it from `from_version`, then wire its own schema and docs
    routes — every version needs both, unconditionally. An unoverridden
    'schema'/'docs' key would keep resolving through the parent's
    Registration unchanged, silently serving the parent's document under
    the child's own path (ADR 0007 item 6); `register()` is used instead
    of `override()` for whichever of the two isn't already resolvable
    through `from_version`'s own chain (`resolved_keys`, its
    `_resolved_keys()`) — a chain with no pre-existing docs route at all
    still gets one wired here, for the developer to build on rather than
    an API silently shipped without one.

    This is the *entire* content `mount` ever generates. A developer never
    hand-writes a version's `derive()` call or its schema/docs wiring —
    `mount` is how a new version starts existing at all; everything past
    this (the version's actual changed endpoints) is a hand-edit to the
    file `mount` just created, the same one-shot-scaffold posture ADR 0003
    item 4 already established for the base version's generated file.
    """
    schema_verb = "override" if "schema/" in resolved_keys else "register"
    docs_verb = "override" if "docs/" in resolved_keys else "register"
    lines = [
        '"""Generated once by `apiver mount`; hand-editable afterwards, like',
        "Django's own `startapp` boilerplate — it is not regenerated on later",
        "runs (ADR 0003 item 4). Add this version's changed endpoints below",
        "with register()/override()/remove().",
        '"""',
        "",
        f"from {root_dir}.{from_version}.registry import {from_version}",
        "",
        f"{version_name} = {from_version}.derive({version_name!r})",
        f"{version_name}.{schema_verb}('schema/', {version_name}.schema_view(prefix={mount_prefix!r}), "
        "name='schema')",
        f"{version_name}.{docs_verb}('docs/', {version_name}.docs_view(), name='docs')",
        "",
    ]
    return "\n".join(lines)


def write_mount(version_name: str, *, from_version: str) -> tuple[Path, Path]:
    """`apiver mount`'s full flow (ticket #47): generate a freshly-authored
    version's `registry.py` from scratch — deriving it from `from_version`
    and wiring its own schema/docs routes — then append its `include()` to
    the Aggregation Root (ADR 0007 item 7). `mount` is the only tool that
    creates a version's `registry.py`, and it does so exactly once:
    refuses if the file already exists, the same posture `init` already
    has for the base version (ADR 0003 item 4) — nothing to regenerate
    from once a developer has started adding their own endpoints to it.

    Never touches `settings.py` — adding `version_name` to `APIVER_VERSIONS`
    stays a hand-edit, consistent with `init` only ever reading settings.

    Returns `(registry_path, aggregation_path)`.
    """
    if not version_name.isidentifier():
        raise InitError(
            f"{version_name!r} is not a valid Python identifier — it becomes the module-level "
            "variable name in the generated registry.py."
        )
    if not from_version.isidentifier():
        raise InitError(f"--from {from_version!r} is not a valid Python identifier.")

    scheme = _configured_scheme()
    display_name = _validate_scheme_conformance(version_name, scheme=scheme)

    root_dir = resolve_root_dir()
    root_prefix = getattr(settings, "APIVER_ROOT_PREFIX", None)
    if root_prefix is None:
        raise InitError(
            "APIVER_ROOT_PREFIX is not set — apiver doesn't know the absolute URL path every "
            "version mounts under (ADR 0007 item 3)."
        )
    root_prefix = root_prefix.lstrip("/")
    _ensure_root_dir_exists(root_dir)

    from_registry_dotted = f"{root_dir}.{from_version}.registry"
    try:
        from_registry_module = import_module(from_registry_dotted)
    except ImportError as exc:
        raise InitError(
            f"{from_registry_dotted!r} could not be imported: {exc}. `--from` must name a version "
            "that has already been mounted, so its registry.py already exists."
        ) from exc
    from_version_obj = getattr(from_registry_module, from_version, None)
    if not isinstance(from_version_obj, Version):
        raise InitError(f"{from_registry_dotted}.{from_version} is not a Version instance.")
    _validate_scheme_conformance(from_version, scheme=scheme, arg_prefix="--from ")

    target_dir = _resolve_target_dir(f"{root_dir}.{version_name}")
    registry_path = target_dir / "registry.py"
    if registry_path.is_file():
        raise InitError(
            f"{registry_path} already exists — mount writes registry.py once and never regenerates "
            "it (ADR 0003 item 4). Hand-edit it directly, or remove it first to regenerate from "
            "scratch."
        )
    # Checked before anything is written, not just inside
    # `_write_or_extend_aggregation_root` at the end — mount must write
    # nothing at all when it can't finish, the same posture `write_init`
    # already takes (ticket 02 recommendation #5).
    if _already_mounted(version_name, root_dir=root_dir):
        aggregation_path = _resolve_target_dir(root_dir) / "urls.py"
        raise InitError(f"{version_name!r} is already mounted in {aggregation_path}.")

    mount_prefix = root_prefix + f"{display_name}/"
    source = render_mount_registry(
        version_name,
        from_version,
        root_dir=root_dir,
        mount_prefix=mount_prefix,
        resolved_keys=from_version_obj._resolved_keys(),
    )

    _ensure_package(target_dir)
    registry_path.write_text(source)

    aggregation_path = _write_or_extend_aggregation_root(
        version_name, root_dir=root_dir, mount_prefix=mount_prefix
    )
    return registry_path, aggregation_path


def write_init(base: str, *, prefix: list[str] | None) -> tuple[Path, Path]:
    """The full `apiver init` flow: resolve where to write, walk the
    live URLconf, classify and verify every in-scope route, then write
    `registry.py` and mount it into the Aggregation Root (ADR 0003 items
    3-4, 7; ADR 0007 items 2, 7). Raises `InitError` — with every
    offending route listed, not just the first — and writes nothing at all
    if any route under `prefix` could not be classified, regenerated, or
    verified.

    `base` is the name `init` adopts the existing project as (`--base`,
    ticket #86) — a one-shot bootstrap input for this single invocation,
    not an ongoing setting: `init` only ever writes `registry.py` once and
    never regenerates it (ADR 0003 item 4), so nothing after this call ever
    needs to read it again.

    `prefix` (ticket #61) is a list of absolute paths — repeatable on the
    CLI (`--prefix`, `action="append"`) — since a real pre-existing
    project's routes are rarely all under one ancestor. Two overlapping
    values (one a prefix of the other, including two identical values) are
    rejected outright: there is no unambiguous way to tell which one a
    route between them belongs to, and the fail-closed posture this module
    takes everywhere else (ticket 02 recommendation #5) applies here too —
    refuse and write nothing rather than guess. `APIVER_ROOT_PREFIX` itself
    stays single-valued regardless — it's a mount-time fact (the one
    absolute path every version mounts under), not a discovery-scope one.

    Returns `(registry_path, aggregation_path)`.
    """
    base_name = base
    if not base_name.isidentifier():
        raise InitError(
            f"--base {base_name!r} is not a valid Python identifier — it becomes the module-level "
            "variable name in the generated registry.py."
        )

    scheme = _configured_scheme()
    display_name = _validate_scheme_conformance(base_name, scheme=scheme)

    root_dir = resolve_root_dir()
    root_prefix = getattr(settings, "APIVER_ROOT_PREFIX", None)
    if root_prefix is None:
        raise InitError(
            "APIVER_ROOT_PREFIX is not set — apiver doesn't know the absolute URL path every version "
            "mounts under (ADR 0007 item 3)."
        )
    root_prefix = root_prefix.lstrip("/")
    _ensure_root_dir_exists(root_dir)

    # `--prefix` — which pre-existing routes count as in scope for adoption
    # — is a distinct fact from APIVER_ROOT_PREFIX, but defaults to it: the
    # common case is that a project's whole pre-existing API already lives
    # under the same absolute path apiver will keep mounting versions at.
    if not prefix:
        prefixes = [root_prefix]
    else:
        # Discovered absolute paths never carry a leading "/" —
        # path()/router declarations don't either — so a user-typed
        # "/api/" is normalized the same as "api/".
        prefixes = [p.lstrip("/") for p in prefix]

    for i, a in enumerate(prefixes):
        for b in prefixes[i + 1 :]:
            if _overlaps(a, b):
                raise InitError(
                    f"--prefix {a!r} and {b!r} overlap — one is a prefix of the other (or they're "
                    "identical), so it's ambiguous which routes between them belong to which. Pass "
                    "only the outer one, or narrow them so neither contains the other."
                )

    module_path = f"{root_dir}.{base_name}"
    target_dir = _resolve_target_dir(module_path)
    registry_path = target_dir / "registry.py"
    if registry_path.is_file():
        raise InitError(
            f"{registry_path} already exists — init writes registry.py once and never regenerates "
            "it (ADR 0003 item 4). Hand-edit it directly, or remove it first to regenerate from "
            "scratch."
        )
    # Checked before anything is written, not just inside
    # `_write_or_extend_aggregation_root` at the end — init must write
    # nothing at all when it can't finish (ticket 02 recommendation #5),
    # and a re-run after only registry.py was removed by hand is exactly
    # the case where the aggregation root already has this mount.
    if _already_mounted(base_name, root_dir=root_dir):
        aggregation_path = _resolve_target_dir(root_dir) / "urls.py"
        raise InitError(f"{base_name!r} is already mounted in {aggregation_path}.")

    mount_prefix = root_prefix + f"{display_name}/"
    root_urlconf = import_module(settings.ROOT_URLCONF)
    result = discover(
        root_urlconf.urlpatterns, prefixes=prefixes, schema_mount_prefix=mount_prefix, base_name=base_name
    )
    if result.diagnostics:
        raise InitError("\n".join(f"- {message}" for message in result.diagnostics))
    # No "nothing discovered" refusal: `discover()` always emits at least
    # the unconditional schema/docs plans, so a genuinely empty greenfield
    # project — no pre-existing routes under `prefix` at all — still gets a
    # valid, if route-less, Base Version out of `init` (ticket #51).

    verify_diagnostics = verify(result, base_name=base_name)
    if verify_diagnostics:
        raise InitError("\n".join(f"- {message}" for message in verify_diagnostics))

    source = render_registry(result.plans, base_name=base_name, var_name=base_name)

    _ensure_package(target_dir)
    registry_path.write_text(source)

    aggregation_path = _write_or_extend_aggregation_root(
        base_name, root_dir=root_dir, mount_prefix=mount_prefix
    )
    return registry_path, aggregation_path


def _extend_aggregation_root_with_alias(
    name: str, from_version: str, *, root_dir: str, alias_prefix: str
) -> Path:
    """Append a new `Alias` declaration and its mount to an already-existing
    Aggregation Root (ticket #53, ADR 0007's second amendment): `from
    apiver.drf import Alias` (once, if not already imported), `<name> =
    Alias(<name>, target=<from_version>)`, and `path(<alias_prefix>,
    <name>.urls)` — no `include()` wrapper, since `Alias.urls` already
    returns one (`version.py`'s `Alias.urls`).

    `write_alias` never calls this against a file that doesn't exist yet:
    aliasing an unmounted `from_version` is refused before this runs, so by
    the time it does, the Aggregation Root already exists in the shape
    `_write_or_extend_aggregation_root` itself generates. Refuses loudly,
    writing nothing, if that shape has drifted — the same posture
    `_write_or_extend_aggregation_root` already takes.
    """
    aggregation_path = _resolve_target_dir(root_dir) / "urls.py"
    source = aggregation_path.read_text()
    lines = source.splitlines()

    import_indices = [i for i, line in enumerate(lines) if line.startswith(("from ", "import "))]
    if not import_indices:
        raise InitError(
            f"{aggregation_path} has no import statements to extend — has it been hand-edited into "
            "an unrecognized shape?"
        )
    if not re.search(r"from apiver\.drf import .*\bAlias\b", source):
        lines.insert(import_indices[-1] + 1, "from apiver.drf import Alias")

    try:
        open_idx = next(i for i, line in enumerate(lines) if line.strip() == "urlpatterns = [")
    except StopIteration:
        raise InitError(
            f"{aggregation_path} has no `urlpatterns = [` list — has it been hand-edited into an "
            "unrecognized shape?"
        ) from None
    lines[open_idx:open_idx] = [f"{name} = Alias({name!r}, target={from_version})", ""]
    open_idx += 2

    try:
        close_idx = next(i for i in range(open_idx + 1, len(lines)) if lines[i].strip() == "]")
    except StopIteration:
        raise InitError(
            f"{aggregation_path}'s urlpatterns list has no closing `]` — has it been hand-edited "
            "into an unrecognized shape?"
        ) from None
    lines.insert(close_idx, f"    path({alias_prefix!r}, {name}.urls),")

    aggregation_path.write_text("\n".join(lines) + "\n")
    return aggregation_path


def write_alias(name: str, *, from_version: str) -> Path:
    """`apiver alias`'s full flow (ticket #53, resolving ADR 0007's second
    amendment): declare a new `Alias` pointing at an already-mounted
    Version, appended straight into the Aggregation Root — an Alias's
    conventional home is the Aggregation Root itself, the same place
    `stable = Alias(...)` already tends to live in practice. No separate
    `registry.py`, no schema/docs wiring of its own: `Alias.urls` already
    re-includes whatever the target Version registered under those keys
    (ADR 0002 items 22-23).

    Refuses if `from_version` names another alias (rather than a Version),
    isn't mounted yet, or if `name` collides with anything already mounted
    under the Aggregation Root's shared prefix namespace — writing nothing
    in every refusal case.

    Never touches `settings.py` — adding `name` to APIVER_ALIASES stays a
    hand-edit, the same posture `write_mount` already takes for
    APIVER_VERSIONS.

    Returns the Aggregation Root's path.
    """
    if not name.isidentifier():
        raise InitError(
            f"{name!r} is not a valid Python identifier — it becomes the module-level variable name "
            "appended to the Aggregation Root."
        )
    if not from_version.isidentifier():
        raise InitError(f"--from {from_version!r} is not a valid Python identifier.")

    root_dir = resolve_root_dir()
    root_prefix = getattr(settings, "APIVER_ROOT_PREFIX", None)
    if root_prefix is None:
        raise InitError(
            "APIVER_ROOT_PREFIX is not set — apiver doesn't know the absolute URL path every "
            "version mounts under (ADR 0007 item 3)."
        )
    root_prefix = root_prefix.lstrip("/")

    # Checked before attempting the import below: an alias never has a
    # registry.py to import in the first place, so without this, `--from`
    # naming an alias would surface as an opaque ImportError instead of the
    # legible "you can't alias an alias" (ticket #53).
    configured_aliases: list[str] = getattr(settings, "APIVER_ALIASES", [])
    if from_version in configured_aliases:
        raise InitError(
            f"--from {from_version!r} names an alias (APIVER_ALIASES), not a Version — an alias "
            "cannot target another alias."
        )

    from_registry_dotted = f"{root_dir}.{from_version}.registry"
    try:
        from_registry_module = import_module(from_registry_dotted)
    except ImportError as exc:
        raise InitError(
            f"{from_registry_dotted!r} could not be imported: {exc}. `--from` must name a version "
            "that has already been mounted, so its registry.py already exists."
        ) from exc
    from_version_obj = getattr(from_registry_module, from_version, None)
    if not isinstance(from_version_obj, Version):
        raise InitError(f"{from_registry_dotted}.{from_version} is not a Version instance.")

    if not _already_mounted(from_version, root_dir=root_dir):
        raise InitError(
            f"{from_version!r} is not mounted in the Aggregation Root — only an already-mounted "
            "version can be aliased."
        )
    if _already_mounted(name, root_dir=root_dir):
        aggregation_path = _resolve_target_dir(root_dir) / "urls.py"
        raise InitError(f"{name!r} is already mounted in {aggregation_path}.")

    # `name` itself stays exempt from scheme validation — a human label
    # (`stable`, `latest`), not a version point (ADR 0008 item 5). Only
    # `--from` names a real version, checked here rather than earlier so
    # every existing-import/already-mounted diagnostic above still fires
    # first for a scheme-nonconforming `--from` that also fails one of
    # those.
    _validate_scheme_conformance(from_version, scheme=_configured_scheme(), arg_prefix="--from ")

    alias_prefix = root_prefix + f"{name}/"
    return _extend_aggregation_root_with_alias(
        name, from_version, root_dir=root_dir, alias_prefix=alias_prefix
    )
