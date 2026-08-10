from dataclasses import dataclass
from typing import Any, Mapping

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

    derive(), override(), remove() and freeze() land in later tickets (#8, #9);
    this ticket is about making register() and its resolution correct for
    every route type, not just router-registered ViewSets.
    """

    def __init__(self, name: str):
        self.name = name
        self._registrations: dict[str, Registration] = {}

    def register(
        self,
        key: str,
        handler: Any,
        *,
        basename: str | None = None,
        name: str | None = None,
    ) -> "Version":
        if key in self._registrations:
            raise ValueError(f"{key!r} is already registered on version {self.name!r}.")

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
        return self

    def _build(self) -> tuple[list, dict[str, Route]]:
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
        return patterns, table

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
        # Base version (no parent yet): bare URL names, no app_name — ADR 0001
        # item 4. Namespacing only applies to authored Versions, built later.
        patterns, _ = self._build()
        return patterns, None
