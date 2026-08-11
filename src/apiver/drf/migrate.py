"""`apiver migrate`: walk the live URLconf and generate the base version's
`registry.py`, mounting it into the Aggregation Root (ticket 17, ADR 0003
items 3-4, 7; ticket 43, ADR 0007). `apiver mount` (`write_mount`) shares
this module: it mounts every later, hand-authored version into that same
Aggregation Root, appending rather than generating from scratch.

Generates wiring only — it never moves a file. The existing
`serializers.py`/`views.py` stay wherever the pre-existing project already
put them; `registry.py` just imports from there and calls `register()`
(ADR 0003 item 3).

This module writes its own URLconf enumerator rather than reusing
drf-spectacular's or DRF's own schema `EndpointEnumerator`. Both are lossy
*schema* filters: `should_include_endpoint` drops every callback without a
`.cls` subclassing `APIView` — every plain Django view, every
`django.views.generic` view, every undecorated function view
(`rest_framework/schemas/generators.py:26-33, 117-118`, ticket 02's
research) — which is exactly the population migrate must not lose. Ground
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
so a bug in prefix derivation fails the `migrate` run instead of shipping a
registry that silently serves the wrong routes (recommendation #5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

from django.conf import settings
from django.urls import URLPattern, URLResolver
from django.urls.resolvers import LocalePrefixPattern, RegexPattern
from drf_spectacular.views import SpectacularAPIView
from rest_framework.routers import APIRootView

from .version import Version

_FORMAT_SUFFIX_RE = re.compile(r"\(\?P<format>|drf_format_suffix")
_MAX_DEPTH = 64


class MigrateError(RuntimeError):
    """One or more routes under `--prefix` could not be classified or
    regenerated. Raised with every offending route listed at once —
    migrate fails closed and writes nothing rather than emit a registry
    that silently drops routes (ticket 02 recommendation #5)."""


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


@dataclass(frozen=True)
class RegistrationPlan:
    """One `register()` call migrate will emit."""

    key: str
    kind: str  # "viewset" | "view" | "schema"
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
    # routes are always `^{prefix}...{trailing_slash}$` — and `path()`'s
    # RoutePattern text never contains them at all. Stripping them
    # unconditionally is safe: neither is legal, unescaped, in a URL path.
    return text.replace("^", "").replace("$", "")


def _overlaps(a: str, b: str) -> bool:
    return a.startswith(b) or b.startswith(a)


def _walk(
    patterns: Any,
    *,
    prefix: str,
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
            if not _overlaps(_strip_anchors(child_prefix), prefix):
                continue  # provably outside --prefix; do not even walk in

            if isinstance(pattern.pattern, LocalePrefixPattern):
                diagnostics.append(
                    "i18n_patterns() found at the URLconf root — its prefix depends on the active "
                    "language at walk time, so the discovered paths would be non-deterministic "
                    "(ticket 02 F14). Not supported by migrate; adopt without i18n_patterns() first, "
                    "or write registry.py by hand."
                )
                continue
            if pattern.namespace is not None:
                diagnostics.append(
                    f"{child_prefix!r} is included under namespace {pattern.namespace!r} — migrate "
                    "only supports the base version's bare, unnamespaced URL names (ADR 0001 item 4, "
                    "ticket 02 F15). Remove the namespace before adopting, or write registry.py by "
                    "hand."
                )
                continue

            _walk(
                pattern.url_patterns,
                prefix=prefix,
                ancestor_prefix=child_prefix,
                depth=depth + 1,
                endpoints=endpoints,
                diagnostics=diagnostics,
            )
        elif isinstance(pattern, URLPattern):
            declared = str(pattern.pattern)
            absolute = _strip_anchors(ancestor_prefix + declared)
            if not absolute.startswith(prefix):
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


def discover(root_patterns: Any, *, prefix: str, schema_mount_prefix: str) -> DiscoveryResult:
    """Walk `root_patterns` (a URLconf's `urlpatterns` list), classify
    every in-scope route, and turn it into a plan for `Version.register()`.

    `schema_mount_prefix` is the base version's full absolute mount path
    (`APIVER_ROOT_PREFIX + f"{base_name}/"`) — known at migrate time since
    ADR 0007 makes it a settings-time fact. It is only ever used to build a
    `schema_view(prefix=...)` plan for a discovered `SpectacularAPIView`
    (ticket #40): the naive `register('schema/', SpectacularAPIView, ...)`
    apiver used to emit is silently wrong the moment a second version
    exists, since that view scans the whole `ROOT_URLCONF` unscoped and
    would start leaking sibling versions' routes.

    `SpectacularSwaggerView`/`SpectacularRedocView` need no equivalent
    special-casing: they never scan the urlconf themselves, only
    `reverse()` the schema route's own `url_name` at request time, so the
    ordinary discovery-and-reimport path below already emits correct
    wiring for them.

    Returns diagnostics for anything that could not be classified or
    regenerated rather than raising immediately — every offending route is
    collected and reported together (ticket 02 recommendation #5).
    """
    endpoints: list[_Endpoint] = []
    diagnostics: list[str] = []
    _walk(
        root_patterns,
        prefix=prefix,
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
        ancestor_relative = _relative(prefix, group[0].ancestor_prefix)
        if "(?P<" in ancestor_relative or "<" in ancestor_relative:
            diagnostics.append(
                f"basename {basename!r} is mounted under a parameterized parent path "
                f"({group[0].ancestor_prefix!r}) — a nested router shape. Nested routers are refused "
                "in 0.1 (ADR 0001 item 5, ticket 02 F7); register it by hand as an explicit path "
                "entry instead."
            )
            continue

        router_prefix = _derive_router_prefix(prefix, basename, group, diagnostics)
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

    schema_endpoints = []
    other_endpoints = []
    for endpoint in view_endpoints:
        if endpoint.cls is not None and issubclass(endpoint.cls, SpectacularAPIView):
            schema_endpoints.append(endpoint)
        else:
            other_endpoints.append(endpoint)
    view_endpoints = other_endpoints

    if len(schema_endpoints) > 1:
        diagnostics.append(
            f"{len(schema_endpoints)} drf-spectacular schema views found under prefix {prefix!r} "
            f"({', '.join(sorted(e.path for e in schema_endpoints))}) — migrate can only auto-wire a "
            "single schema endpoint per version (ticket #40). Remove the extras, or register them by "
            "hand with Version.schema_view(prefix=...)."
        )
    elif schema_endpoints:
        endpoint = schema_endpoints[0]
        if endpoint.cls is not SpectacularAPIView:
            diagnostics.append(
                f"{endpoint.path!r} is served by {endpoint.cls.__module__}.{endpoint.cls.__qualname__}, "
                "a drf-spectacular schema view subclass (e.g. SpectacularYAMLAPIView/"
                "SpectacularJSONAPIView) — migrate only auto-wires the exact, content-negotiated "
                "SpectacularAPIView (ticket #40). Register it by hand with "
                "Version.schema_view(prefix=...)."
            )
        elif endpoint.url_name is None:
            diagnostics.append(
                f"{endpoint.path!r} has no url `name=` — register() requires an explicit name= for "
                "non-ViewSet handlers, since there is no router to derive one from (ADR 0002 item 3)."
            )
        elif endpoint.is_regex_declared:
            diagnostics.append(
                f"{endpoint.path!r} was declared with re_path(), not path() — apiver's register() "
                "always re-emits explicit views as path() entries, which cannot express an arbitrary "
                "regex (ticket 02 §3.5). Convert it to path() first, or register it by hand."
            )
        else:
            key = _relative(prefix, endpoint.path)
            groups[key] = [endpoint]
            plans.append(
                RegistrationPlan(
                    key=key,
                    kind="schema",
                    module="",
                    symbol="",
                    name=endpoint.url_name,
                    schema_prefix=schema_mount_prefix,
                )
            )

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

        key = _relative(prefix, endpoint.path)
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
    matters specifically for migrate — that the *count* of routes produced
    under a derived key matches what was discovered there, catching a
    wrong router-prefix derivation that would otherwise silently register
    the right class under the wrong path.
    """
    version = Version(base_name)
    try:
        for plan in result.plans:
            if plan.kind == "schema":
                handler = version.schema_view(prefix=plan.schema_prefix)
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
        produced = [
            route
            for route in table.values()
            if route.registration is not None and route.registration.key == plan.key
        ]
        expected = len(result._groups.get(plan.key, []))
        if len(produced) != expected:
            diagnostics.append(
                f"verification failed for key {plan.key!r}: discovered {expected} route(s) but "
                f"registering it produced {len(produced)} — migrate's prefix derivation likely made "
                "a mistake; refusing to write a broken registry.py."
            )
    return diagnostics


def render_registry(plans: list[RegistrationPlan], *, base_name: str, var_name: str) -> str:
    """Render `registry.py`'s source text. Deterministic: plans are
    processed in the sorted-by-key order `discover()` already returns them
    in, so two runs against the same URLconf produce byte-identical
    output.
    """
    imports: dict[str, list[str]] = {}
    for plan in plans:
        if plan.kind != "schema":  # no import needed — the handler is {var_name}.schema_view(...)
            imports.setdefault(plan.module, []).append(plan.symbol)

    import_lines = [
        f"from {module} import {', '.join(sorted(set(symbols)))}"
        for module, symbols in sorted(imports.items())
    ]

    register_lines = []
    for plan in plans:
        if plan.kind == "viewset":
            register_lines.append(
                f"{var_name}.register({plan.key!r}, {plan.symbol}, basename={plan.basename!r})"
            )
        elif plan.kind == "schema":
            register_lines.append(
                f"{var_name}.register({plan.key!r}, {var_name}.schema_view(prefix={plan.schema_prefix!r}), "
                f"name={plan.name!r})"
            )
        else:
            register_lines.append(f"{var_name}.register({plan.key!r}, {plan.symbol}, name={plan.name!r})")

    lines = [
        '"""Generated once by `apiver migrate`; hand-editable afterwards, like',
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
        raise MigrateError(f"{parent_path!r} is a module, not a package — it cannot contain {leaf!r}.")
    return Path(next(iter(parent_dir))) / leaf


def render_aggregation_root(mounts: list[tuple[str, str]], *, root_dir: str) -> str:
    """Render the Aggregation Root's `urls.py` source (ADR 0007 item 2):
    one `include()` per Live Version, each already carrying its full
    absolute mount path. `mounts` is `[(version_name, absolute_prefix),
    ...]`, in the order they should appear.

    Used to render the *initial* file only — by `migrate` for the base
    version, or by `apiver mount` seeding the very first mount in a
    greenfield project. Every mount after that is appended in place by
    `_write_or_extend_aggregation_root`, never re-rendered from scratch, so
    a developer's hand edits to this file survive.
    """
    import_lines = [f"from {root_dir}.{name}.registry import {name}" for name, _ in mounts]
    mount_lines = [f"    path({prefix!r}, include({name}.urls))," for name, prefix in mounts]
    lines = [
        '"""Generated by `apiver migrate`; extended in place by `apiver mount`',
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


def _already_mounted(version_name: str, *, root_dir: str) -> bool:
    aggregation_path = _resolve_target_dir(root_dir) / "urls.py"
    if not aggregation_path.is_file():
        return False
    return re.search(rf"include\({re.escape(version_name)}\.urls\)", aggregation_path.read_text()) is not None


def _write_or_extend_aggregation_root(version_name: str, *, root_dir: str, mount_prefix: str) -> Path:
    """Mount `version_name` into `<root_dir>/urls.py`, creating the
    Aggregation Root (and its package, if needed) on the very first call —
    shared by `migrate` (the base version's initial mount, ADR 0007 item 7)
    and `apiver mount` (every authored version after, including as the
    first-ever mount in a greenfield project that never ran migrate).

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
        raise MigrateError(f"{version_name!r} is already mounted in {aggregation_path}.")

    lines = source.splitlines()
    import_indices = [i for i, line in enumerate(lines) if line.startswith(("from ", "import "))]
    if not import_indices:
        raise MigrateError(
            f"{aggregation_path} has no import statements to extend — has it been hand-edited into "
            "an unrecognized shape?"
        )
    lines.insert(import_indices[-1] + 1, f"from {root_dir}.{version_name}.registry import {version_name}")

    try:
        open_idx = next(i for i, line in enumerate(lines) if line.strip() == "urlpatterns = [")
    except StopIteration:
        raise MigrateError(
            f"{aggregation_path} has no `urlpatterns = [` list — has it been hand-edited into an "
            "unrecognized shape?"
        ) from None
    try:
        close_idx = next(i for i in range(open_idx + 1, len(lines)) if lines[i].strip() == "]")
    except StopIteration:
        raise MigrateError(
            f"{aggregation_path}'s urlpatterns list has no closing `]` — has it been hand-edited into "
            "an unrecognized shape?"
        ) from None
    lines.insert(close_idx, f"    path({mount_prefix!r}, include({version_name}.urls)),")

    aggregation_path.write_text("\n".join(lines) + "\n")
    return aggregation_path


def write_mount(version_name: str) -> Path:
    """`apiver mount`'s full flow: append an already-authored version's
    `include()` to the Aggregation Root (ADR 0007 item 7). Never touches
    `settings.py` — adding `version_name` to `APIVER_VERSIONS` stays a
    hand-edit, consistent with `migrate` only ever reading settings.
    """
    if not version_name.isidentifier():
        raise MigrateError(
            f"{version_name!r} is not a valid Python identifier — it must match the module-level "
            "variable name in the version's own registry.py."
        )

    root_dir = getattr(settings, "APIVER_ROOT_DIR", None)
    if not root_dir:
        raise MigrateError(
            "APIVER_ROOT_DIR is not set — apiver doesn't know where the aggregation root lives "
            "(ADR 0007 item 3)."
        )
    root_prefix = getattr(settings, "APIVER_ROOT_PREFIX", None)
    if root_prefix is None:
        raise MigrateError(
            "APIVER_ROOT_PREFIX is not set — apiver doesn't know the absolute URL path every "
            "version mounts under (ADR 0007 item 3)."
        )
    root_prefix = root_prefix.lstrip("/")

    registry_dotted = f"{root_dir}.{version_name}.registry"
    try:
        registry_module = import_module(registry_dotted)
    except ImportError as exc:
        raise MigrateError(
            f"{registry_dotted!r} could not be imported: {exc}. `apiver mount` expects the version's "
            "registry.py to already exist — write it by hand first (ADR 0003 item 3), or run "
            "`apiver migrate` first for the base version."
        ) from exc
    version_obj = getattr(registry_module, version_name, None)
    if not isinstance(version_obj, Version):
        raise MigrateError(f"{registry_dotted}.{version_name} is not a Version instance.")

    return _write_or_extend_aggregation_root(
        version_name, root_dir=root_dir, mount_prefix=root_prefix + f"{version_name}/"
    )


def write_registry(*, prefix: str | None) -> tuple[Path, Path]:
    """The full `apiver migrate` flow: resolve where to write, walk the
    live URLconf, classify and verify every in-scope route, then write
    `registry.py` and mount it into the Aggregation Root (ADR 0003 items
    3-4, 7; ADR 0007 items 2, 7). Raises `MigrateError` — with every
    offending route listed, not just the first — and writes nothing at all
    if any route under `prefix` could not be classified, regenerated, or
    verified.

    Returns `(registry_path, aggregation_path)`.
    """
    base_name = getattr(settings, "APIVER_BASE_VERSION", None)
    if not base_name:
        raise MigrateError(
            "APIVER_BASE_VERSION is not set — apiver doesn't know which version `migrate` is adopting "
            "the project as. Set it in settings, alongside APIVER_ROOT_DIR (ADR 0007 item 3)."
        )
    if not base_name.isidentifier():
        raise MigrateError(
            f"APIVER_BASE_VERSION={base_name!r} is not a valid Python identifier — it becomes the "
            "module-level variable name in the generated registry.py."
        )

    root_dir = getattr(settings, "APIVER_ROOT_DIR", None)
    if not root_dir:
        raise MigrateError(
            "APIVER_ROOT_DIR is not set — apiver doesn't know where to write registry.py. Set it to "
            "the dotted path of the aggregation root package (ADR 0007 item 3)."
        )
    root_prefix = getattr(settings, "APIVER_ROOT_PREFIX", None)
    if root_prefix is None:
        raise MigrateError(
            "APIVER_ROOT_PREFIX is not set — apiver doesn't know the absolute URL path every version "
            "mounts under (ADR 0007 item 3)."
        )
    root_prefix = root_prefix.lstrip("/")

    # `--prefix` — which pre-existing routes count as in scope for adoption
    # — is a distinct fact from APIVER_ROOT_PREFIX, but defaults to it: the
    # common case is that a project's whole pre-existing API already lives
    # under the same absolute path apiver will keep mounting versions at.
    if prefix is None:
        prefix = root_prefix
    # Discovered absolute paths never carry a leading "/" — path()/router
    # declarations don't either — so a user-typed "/api/" is normalized the
    # same as "api/".
    prefix = prefix.lstrip("/")

    module_path = f"{root_dir}.{base_name}"
    target_dir = _resolve_target_dir(module_path)
    registry_path = target_dir / "registry.py"
    if registry_path.is_file():
        raise MigrateError(
            f"{registry_path} already exists — migrate writes registry.py once and never regenerates "
            "it (ADR 0003 item 4). Hand-edit it directly, or remove it first to regenerate from "
            "scratch."
        )
    # Checked before anything is written, not just inside
    # `_write_or_extend_aggregation_root` at the end — migrate must write
    # nothing at all when it can't finish (ticket 02 recommendation #5),
    # and a re-run after only registry.py was removed by hand is exactly
    # the case where the aggregation root already has this mount.
    if _already_mounted(base_name, root_dir=root_dir):
        aggregation_path = _resolve_target_dir(root_dir) / "urls.py"
        raise MigrateError(f"{base_name!r} is already mounted in {aggregation_path}.")

    mount_prefix = root_prefix + f"{base_name}/"
    root_urlconf = import_module(settings.ROOT_URLCONF)
    result = discover(root_urlconf.urlpatterns, prefix=prefix, schema_mount_prefix=mount_prefix)
    if result.diagnostics:
        raise MigrateError("\n".join(f"- {message}" for message in result.diagnostics))
    if not result.plans:
        raise MigrateError(f"no routes discovered under prefix {prefix!r} — nothing to migrate.")

    verify_diagnostics = verify(result, base_name=base_name)
    if verify_diagnostics:
        raise MigrateError("\n".join(f"- {message}" for message in verify_diagnostics))

    source = render_registry(result.plans, base_name=base_name, var_name=base_name)

    target_dir.mkdir(parents=True, exist_ok=True)
    init_file = target_dir / "__init__.py"
    if not init_file.is_file():
        init_file.write_text("")
    registry_path.write_text(source)

    aggregation_path = _write_or_extend_aggregation_root(
        base_name, root_dir=root_dir, mount_prefix=mount_prefix
    )
    return registry_path, aggregation_path
