from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from typing import Any

from django.http import JsonResponse
from django.urls import URLPattern, include, path
from django.utils import timezone
from django.utils.http import http_date
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import BaseRouter, SimpleRouter
from rest_framework.viewsets import ViewSetMixin

from .fields import check_no_removed_fields


class CompositionError(RuntimeError):
    """The patterns apiver built don't match what its registrations intended.

    Signals a bug in apiver's own composition, not a mistake in the caller's
    registrations — the self-verifying re-walk from ADR 0001 item 5.
    """


@dataclass(frozen=True)
class RouteIdentity:
    """Metadata read off a resolved route — never inferred from the handler class.

    `ViewSetMixin.as_view()` resets `cls.basename`/`cls.detail`/`cls.suffix` to
    None on every call, so introspecting the class after the fact would return
    stale values left by an unrelated registration (ADR 0001 item 2). This is
    read from the built callback's `initkwargs`/`actions` instead.
    """

    basename: str | None
    action: Mapping[str, str] | None
    detail: bool | None
    url_name: str | None
    methods: frozenset[str]


@dataclass(frozen=True)
class Registration:
    """One declaration binding a handler into a Version.

    Keyed by router prefix for ViewSets, by literal path for everything else
    (ADR 0002 item 3).
    """

    key: str
    kind: str  # "viewset" | "view"
    handler: Any
    basename: str | None = None
    name: str | None = None
    # The Version that created this Registration, fixed at register()/
    # override() time. Inherited routes reuse this same object by identity
    # (ADR 0002 item 6), so it survives unchanged as the manifest's
    # source_version even when a route is resolved through a descendant
    # that never touched the key (ticket 16, ADR 0003 item 6).
    source_version: str = ""


@dataclass(frozen=True)
class Route:
    """One entry in a Version's resolution table, keyed by its path pattern.

    A ViewSet Registration expands into several Routes; every Route traces
    back to exactly one Registration (ADR 0001 item 3), which is what makes a
    whole registration — not a single path — the unit of override and removal.
    """

    identity: RouteIdentity
    registration: Registration


def _classify(handler: Any) -> str:
    is_router = (isinstance(handler, type) and issubclass(handler, BaseRouter)) or isinstance(
        handler, BaseRouter
    )
    if is_router:
        raise TypeError(
            f"{handler!r} is a router, not a ViewSet or view. Nested routers are "
            "refused — register the ViewSet(s) it wraps directly (ADR 0001 item 5)."
        )
    if isinstance(handler, type) and issubclass(handler, ViewSetMixin):
        return "viewset"
    return "view"


def _path_str(url_pattern: Any) -> str:
    # SimpleRouter emits RegexPattern (declared as regex); path() emits
    # RoutePattern (declared as route syntax). str() on each renders in its own
    # declaration style, so two routes could carry the same path under
    # different-looking keys. `.regex.pattern` is the compiled form both
    # pattern types resolve to, giving one consistent key space.
    return url_pattern.pattern.regex.pattern


def _route_identity(url_pattern: Any) -> RouteIdentity:
    callback = url_pattern.callback
    actions = getattr(callback, "actions", None)
    if actions is not None:
        initkwargs = getattr(callback, "initkwargs", {})
        return RouteIdentity(
            basename=initkwargs.get("basename"),
            action=dict(actions),
            detail=initkwargs.get("detail"),
            url_name=url_pattern.name,
            methods=frozenset(method.upper() for method in actions),
        )

    cls = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    methods = (
        frozenset(method.upper() for method in cls.http_method_names if hasattr(cls, method))
        if cls is not None
        else frozenset()
    )
    return RouteIdentity(
        basename=None,
        action=None,
        detail=None,
        url_name=url_pattern.name,
        methods=methods,
    )


class Version:
    """A named surface of the API, composed from Registrations.

    A Version with a parent composes its parent's resolution table alongside
    its own, walked fresh at build time (ADR 0002 item 2) rather than copied
    at derive() time. It stays mutable — register()/override()/remove() all
    work — until freeze() is called (ADR 0002 item 2).
    """

    def __init__(self, name: str):
        self.name = name
        self.parent: Version | None = None
        self._registrations: dict[str, Registration] = {}
        self._removed: set[str] = set()
        self._frozen = False
        self._deprecated = False
        self._sunset_at: datetime | None = None
        self._own_build_cache: tuple[list, dict[str, Route]] | None = None
        self._schema_view_cache: Any | None = None

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def deprecated(self) -> bool:
        return self._deprecated

    @property
    def sunset_at(self) -> datetime | None:
        return self._sunset_at

    def derive(self, name: str) -> "Version":
        """Return a new Version whose parent is `self`.

        Not a constructor kwarg (ADR 0002 item 1) — the parent is set by the
        verb, so lineage order can't be passed out of sequence. `self` need
        not be frozen, and may be derived from any number of times; each
        child walks `self` live at composition time, so branching falls out
        without special-casing (ADR 0002 item 2).
        """
        child = Version(name)
        child.parent = self
        return child

    def _resolved_keys(self) -> set[str]:
        """Keys currently resolvable through this Version, respecting removals.

        A key removed here (or by an ancestor, at its own level) no longer
        counts as present, so it can be re-registered from scratch.
        """
        keys = set(self._registrations)
        if self.parent is not None:
            keys |= self.parent._resolved_keys() - self._removed
        return keys

    def _check_not_frozen(self, verb: str) -> None:
        if self._frozen:
            raise RuntimeError(f"version {self.name!r} is frozen and cannot be {verb}.")

    def _check_suffix(self, verb: str, handler: Any) -> None:
        """Refuse a class-based handler whose name doesn't carry this
        Version's suffix (ticket 11, ADR 0003 item 2).

        drf-spectacular derives component and operation-id names from
        `__class__.__name__` alone, with no awareness of which version module
        a class lives in — so two same-named classes registered under
        different versions silently collide, and the second one's schema is
        dropped in favor of the first's (ADR 0003, ticket 03's finding).
        Checked here, at register()/override() time, because the call
        already holds the class object; no stack-frame introspection needed.

        The Base Version (no parent) is exempt: it's the developer's
        existing, unmodified API, and forcing a rename onto it would violate
        the promise that adopting apiver leaves V1's code exactly where it
        is. Non-class handlers (plain functions) are exempt too — there is
        no `__name__` naming convention to enforce for those.
        """
        if self.parent is None or not isinstance(handler, type):
            return
        suffix = self.name.upper()
        if suffix not in handler.__name__:
            raise ValueError(
                f"{handler.__name__!r} does not carry version {self.name!r}'s "
                f"suffix ({suffix!r}) in its name, so it cannot be {verb} on "
                f"version {self.name!r}. drf-spectacular names components and "
                "operations after the class name alone, so a same-named class "
                "in a different version module would silently emit the wrong "
                "schema (ADR 0003 item 2). Rename the class to include "
                f"{suffix!r}."
            )

    def _check_no_removed_fields(self, handler: Any) -> None:
        """Refuse a handler whose `serializer_class` sets an inherited field
        to `None` (ticket 14, ADR 0006 item 1) — DRF's silent footgun where
        the field can survive removal in both the response body and the
        schema. Checked here, alongside `_check_suffix`, because register()
        and override() are the only points where apiver ever sees the
        handler class."""
        serializer_class = getattr(handler, "serializer_class", None)
        if serializer_class is not None:
            check_no_removed_fields(serializer_class)

    def register(
        self,
        key: str,
        handler: Any,
        *,
        basename: str | None = None,
        name: str | None = None,
    ) -> "Version":
        """Bind a new key. Raises if the key already exists anywhere up the
        parent chain — use override() to replace an existing Registration
        (ADR 0002 item 3)."""
        self._check_not_frozen("mutated")
        if key in self._resolved_keys():
            raise ValueError(
                f"{key!r} is already registered on version {self.name!r} or one of its ancestors. "
                "Use override() to replace it."
            )

        kind = _classify(handler)
        self._check_suffix("registered", handler)
        self._check_no_removed_fields(handler)
        if kind == "view":
            if name is None:
                raise TypeError(
                    f"registering {handler!r} at {key!r} requires an explicit name= "
                    "— there is no router to derive one from (ADR 0002 item 3)."
                )
        else:
            basename = basename or key

        self._registrations[key] = Registration(
            key=key, kind=kind, handler=handler, basename=basename, name=name, source_version=self.name
        )
        self._own_build_cache = None
        return self

    def override(
        self,
        key: str,
        handler: Any,
        *,
        basename: str | None = None,
        name: str | None = None,
    ) -> "Version":
        """Replace an existing Registration. Raises if the key doesn't exist
        anywhere up the parent chain — use register() for a genuinely new key
        (ADR 0002 item 3). The whole Registration is replaced, so every path
        it previously expanded into is replaced too (ADR 0001 item 3); a
        narrower, sub-route override isn't expressible through this key space
        by design."""
        self._check_not_frozen("mutated")
        if key not in self._resolved_keys():
            raise ValueError(
                f"{key!r} is not registered on version {self.name!r} or any of its "
                "ancestors, so it cannot be overridden. Use register() to add it."
            )

        kind = _classify(handler)
        self._check_suffix("overridden", handler)
        self._check_no_removed_fields(handler)
        if kind == "view":
            if name is None:
                raise TypeError(
                    f"overriding {handler!r} at {key!r} requires an explicit name= "
                    "— there is no router to derive one from (ADR 0002 item 3)."
                )
        else:
            basename = basename or key

        self._registrations[key] = Registration(
            key=key, kind=kind, handler=handler, basename=basename, name=name, source_version=self.name
        )
        self._own_build_cache = None
        return self

    def remove(self, key: str) -> "Version":
        """Erase a Registration from this Version's resolved surface. Raises
        if the key isn't present in the resolved parent chain (ADR 0002 item
        4) — a removal that silently does nothing must not be shippable. An
        ancestor keeps serving the key; only this Version and its descendants
        stop."""
        self._check_not_frozen("mutated")
        if key not in self._resolved_keys():
            raise ValueError(
                f"{key!r} is not registered on version {self.name!r} or any of its "
                "ancestors, so it cannot be removed."
            )

        self._registrations.pop(key, None)
        self._removed.add(key)
        self._own_build_cache = None
        return self

    def freeze(self) -> "Version":
        """End this Version's mutability, one-way (ADR 0002 item 2). After
        this, register()/override()/remove() all raise. derive() is
        unaffected — freezing a parent is independent of branching from it."""
        self._frozen = True
        return self

    def deprecate(self, *, sunset: datetime) -> "Version":
        """Marks this Version deprecated with a sunset date (ticket 13, ADR
        0002 item 5).

        Lives on the `Version` object, never in settings or the manifest, so
        there is exactly one source of truth for a Version's lifecycle. Takes
        effect through the mount-time wrapper `urls` builds: every response
        from this Version's mount carries `Deprecation: true` and `Sunset:
        <HTTP-date>`, and requests made after `sunset` (evaluated on the wall
        clock at request time, not here) get `410 Gone` instead of reaching
        the view. Independent of `freeze()` — deprecation is a lifecycle
        fact, not a mutability one."""
        self._deprecated = True
        self._sunset_at = sunset
        return self

    def _gate(self, callback: Any) -> Any:
        """Wrap a callback with this Version's deprecation/sunset gating.

        Closes directly over `self` rather than reverse-engineering which
        Version served a request from `request.resolver_match` — the latter
        breaks specifically for the unnamespaced base Version (ticket 13).
        `@wraps` copies the original callback's `__dict__`, which is where
        DRF's `.as_view()` stashes `cls`/`actions`/`initkwargs` — without
        that, drf-spectacular's schema generation (which walks this same
        `urls`) couldn't introspect the wrapped view.
        """

        @wraps(callback)
        def gated(request, *args, **kwargs):
            if self._sunset_at is not None and timezone.now() >= self._sunset_at:
                return JsonResponse({"detail": "This API version has been sunset."}, status=410)
            response = callback(request, *args, **kwargs)
            response["Deprecation"] = "true"
            if self._sunset_at is not None:
                response["Sunset"] = http_date(self._sunset_at.timestamp())
            return response

        return gated

    def _build_own(self) -> tuple[list, dict[str, Route]]:
        if self._own_build_cache is not None:
            return self._own_build_cache

        router = SimpleRouter()
        view_patterns = []
        registrations_by_basename: dict[str, Registration] = {}
        registrations_by_name: dict[str, Registration] = {}
        for registration in self._registrations.values():
            if registration.kind == "viewset":
                router.register(registration.key, registration.handler, basename=registration.basename)
                registrations_by_basename[registration.basename] = registration
            else:
                callback = (
                    registration.handler.as_view()
                    if isinstance(registration.handler, type)
                    else registration.handler
                )
                view_patterns.append(path(registration.key, callback, name=registration.name))
                registrations_by_name[registration.name] = registration

        # Explicit view patterns before router patterns: SimpleRouter's detail
        # regex is generic enough to swallow a sibling path like
        # "payments/summary/" as pk="summary" if tried first (ticket 05 finding 2).
        patterns = view_patterns + router.urls
        table: dict[str, Route] = {}
        for pattern in patterns:
            identity = _route_identity(pattern)
            registration = (
                registrations_by_basename.get(identity.basename)
                if identity.basename is not None
                else registrations_by_name.get(identity.url_name)
            )
            table[_path_str(pattern)] = Route(identity=identity, registration=registration)

        self._verify(table)
        self._own_build_cache = (patterns, table)
        return self._own_build_cache

    def _build(self) -> tuple[list, dict[str, Route]]:
        own_patterns, own_table = self._build_own()
        if self.parent is None:
            return own_patterns, own_table

        # Live composition (ADR 0002 item 2): re-walk the parent on every
        # build rather than snapshotting at derive() time, so registrations
        # added to a still-mutable parent are visible immediately. The
        # parent's own patterns/table are cached at *its* level and only
        # invalidated by its own mutations, so unchanged entries — the
        # inherited callback objects and their Route metadata — are the same
        # objects across separate builds, not rebuilt copies.
        parent_patterns, parent_table = self.parent._build()

        # Shadowed keys (removed, or overridden by an own registration) drop
        # their parent's paths entirely rather than being merged over: an
        # override whose new shape has fewer routes than the parent's must
        # not leave stale parent-only paths behind (ADR 0001 item 3).
        shadowed = self._removed | set(self._registrations)
        if shadowed:
            parent_table = {
                path: route
                for path, route in parent_table.items()
                if route.registration is None or route.registration.key not in shadowed
            }
            parent_patterns = [pattern for pattern in parent_patterns if _path_str(pattern) in parent_table]

        combined_table = {**parent_table, **own_table}
        combined_patterns = own_patterns + parent_patterns
        return combined_patterns, combined_table

    def _verify(self, table: dict[str, Route]) -> None:
        produced = {route.registration for route in table.values() if route.registration is not None}
        unaccounted_paths = [path for path, route in table.items() if route.registration is None]
        missing_keys = [
            registration.key for registration in self._registrations.values() if registration not in produced
        ]
        if unaccounted_paths or missing_keys:
            raise CompositionError(
                f"composition for version {self.name!r} does not match its registrations: "
                f"missing={missing_keys!r} unaccounted_paths={unaccounted_paths!r}"
            )

    @property
    def resolution_table(self) -> dict[str, Route]:
        _, table = self._build()
        return table

    @property
    def urls(self):
        # Base version (no parent): bare URL names, no app_name (ADR 0001
        # item 4). A derived Version is mounted under a Django instance
        # namespace matching its own name, so `include(v2.urls)` needs no
        # explicit namespace= to make `reverse("v2:...")` work (ADR 0002
        # item 7).
        patterns, _ = self._build()
        if self._deprecated:
            # A fresh list of patterns wrapping this Version's own callbacks,
            # not a mutation of `_build()`'s cache: the same route inherited
            # by a non-deprecated child (or reused unchanged by the parent's
            # own resolution table) must not pick up this Version's gating.
            patterns = [
                URLPattern(pattern.pattern, self._gate(pattern.callback), pattern.default_args, pattern.name)
                for pattern in patterns
            ]
        app_name = self.name if self.parent is not None else None
        return patterns, app_name

    @property
    def schema_route_name(self) -> str:
        """The `name=` this Version's own `schema_view()` registration
        should always use — the single source of that convention:
        `apiver migrate` derives a discovered schema route's name from it,
        and `docs_view()` below reverses it by name, rather than either
        duplicating the string format independently (ticket 22 finding: the
        two drifting out of sync is exactly how a Swagger/Redoc UI silently
        ends up pointing at the wrong version's schema).

        The Base Version has no Django instance namespace of its own (ADR
        0001 item 4) — a bare "schema" name would collide with a
        pre-existing, identically-named route kept mounted alongside it
        (ticket 22 finding), so it needs its own explicitly qualified name,
        `f"{name}-schema"`. An authored Version already gets an instance
        namespace for free (ADR 0002 item 7, `app_name=self.name` on
        `Version.urls`) — Django prefixes *any* name registered inside it
        with `f"{name}:"` automatically, so qualifying the registration name
        itself would only double up (`f"{name}:{name}-schema"`); it stays
        registered under the plain "schema" every version already used.
        """
        return f"{self.name}-schema" if self.parent is None else "schema"

    def schema_view(
        self,
        *,
        prefix: str | None = None,
        title: str | None = None,
        description: str | None = None,
        version: str | None = None,
    ):
        """A view serving this Version's own OpenAPI document, and nothing
        else's.

        `prefix` is the exact first argument passed to the `path()` this
        Version is mounted under (e.g. `"api/v2/"`) — it re-derives the
        version's absolute URLs for the generator and pins
        `SCHEMA_PATH_PREFIX` from it, since the auto-estimated prefix drifts
        with every route added or removed (ADR 0002 Consequences, ticket 10).
        Built as `APIVER_ROOT_PREFIX + f"{name}/"` — the one place that
        absolute string is defined (ADR 0007 item 6) — by whatever wires a
        version's schema route; `apiver migrate` does this for the base
        version's generated `registry.py` today.
        The generator is built with `patterns=` scoped to exactly this
        Version's own mounted patterns — not the whole project's urlconf —
        so sibling versions' routes can never leak in and drf-spectacular's
        `(path, method)`-keyed dedup can never collide across versions (ADR
        0002 Consequences).

        Cached after the first call, and every later call — regardless of
        arguments — returns that exact same view object. This is what lets
        `Alias.schema_view()` (ticket 12) proxy straight through to a
        target's `schema_view()` with no arguments of its own and still get
        back the identical instance the target mounted for itself, rather
        than building a second, independently-generated document. `prefix`
        is only required on the first, cache-populating call.
        """
        if self._schema_view_cache is not None:
            return self._schema_view_cache

        if prefix is None:
            raise TypeError(
                f"version {self.name!r} has no schema view yet — the first "
                "schema_view() call must pass prefix= (ADR 0002 Consequences)."
            )

        mount = [path(prefix, include(self.urls))]
        custom_settings = {"SCHEMA_PATH_PREFIX": "/" + prefix.strip("/")}
        if title is not None:
            custom_settings["TITLE"] = title
        if description is not None:
            custom_settings["DESCRIPTION"] = description
        custom_settings["VERSION"] = version if version is not None else self.name
        self._schema_view_cache = SpectacularAPIView.as_view(patterns=mount, custom_settings=custom_settings)
        return self._schema_view_cache

    def docs_view(self, *, view_class: type = SpectacularSwaggerView):
        """A Swagger/Redoc-style UI view pointed at this Version's own schema
        route — the same call shape as `schema_view()` (called on the
        `Version`, not built ad hoc at the call site), even though there's
        no scoping problem to solve here: neither `SpectacularSwaggerView`
        nor `SpectacularRedocView` scans the urlconf themselves, they only
        `reverse()` a schema route's name at request time (ticket 22).

        Resolves `schema_route_name` into the actual string `reverse()`
        needs, which is *not* always the same string schema_view()'s own
        registration used: an authored Version's instance namespace means
        anything reversing its schema route from outside that namespace —
        including this view, since a UI page isn't itself inside the
        namespace at request-resolution time — needs the qualified
        `f"{self.name}:{schema_route_name}"` form, not the bare local name
        the registration itself was given.

        Not cached, unlike `schema_view()` — a schema document is singular
        per Version by design (ADR 0002 Consequences), but a UI in front of
        it isn't: a project can mount both a Swagger view and a Redoc view
        against the identical schema, each its own registration, so caching
        a single result here would silently return the wrong one on a
        second call with a different `view_class`.
        """
        reverse_name = self.schema_route_name
        if self.parent is not None:
            reverse_name = f"{self.name}:{reverse_name}"
        return view_class.as_view(url_name=reverse_name)


class Alias:
    """A movable name that resolves through a target Version's exact mounts.

    Declared independently of `Version` (ADR 0002 item 8) — an alias points
    *at* a Version without being owned by one, and is re-pointed by editing
    `target=`. Mounting it reuses the target's exact callback objects at a
    second prefix rather than a fresh registration, so an alias can never
    drift from the version it names.

    A broken target (an undefined name, an import that failed) fails at
    Python import time before `Alias` ever runs — there is no request-time
    "alias points nowhere" case to gate here.

    `schema_view()`/`docs_view()` are plain proxies to the target's own
    (see those methods' docstrings) — promoting the alias to a new target
    only ever means editing `target=` here; nothing at the alias's own
    mount site has to change.
    """

    def __init__(self, name: str, *, target: Version):
        self.name = name
        self.target = target

    def schema_view(self):
        return self.target.schema_view()

    def docs_view(self, *, view_class: type = SpectacularSwaggerView):
        return self.target.docs_view(view_class=view_class)

    @property
    def urls(self):
        # The target's own patterns are reused unchanged; only the
        # *instance* namespace differs (ADR 0002 item 8) — `namespace=`
        # here, distinct from the `target.name` app_name, is what makes
        # `reverse("stable:...")` and `reverse("v2:...")` resolve
        # independently for the identical view. Without it, `include()`
        # would default the instance namespace to the app_name and
        # "stable:..." would never resolve.
        patterns, _ = self.target.urls
        return include((patterns, self.target.name), namespace=self.name)
