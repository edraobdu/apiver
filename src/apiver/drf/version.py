from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from django.urls import path
from rest_framework.routers import BaseRouter, SimpleRouter
from rest_framework.viewsets import ViewSetMixin


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
        self._own_build_cache: tuple[list, dict[str, Route]] | None = None

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
                f"{key!r} is already registered on version {self.name!r} or one of its ancestors."
            )

        kind = _classify(handler)
        if kind == "view":
            if name is None:
                raise TypeError(
                    f"registering {handler!r} at {key!r} requires an explicit name= "
                    "— there is no router to derive one from (ADR 0002 item 3)."
                )
        else:
            basename = basename or key

        self._registrations[key] = Registration(
            key=key, kind=kind, handler=handler, basename=basename, name=name
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
                "ancestors, so it cannot be overridden."
            )

        kind = _classify(handler)
        if kind == "view":
            if name is None:
                raise TypeError(
                    f"overriding {handler!r} at {key!r} requires an explicit name= "
                    "— there is no router to derive one from (ADR 0002 item 3)."
                )
        else:
            basename = basename or key

        self._registrations[key] = Registration(
            key=key, kind=kind, handler=handler, basename=basename, name=name
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
        app_name = self.name if self.parent is not None else None
        return patterns, app_name
