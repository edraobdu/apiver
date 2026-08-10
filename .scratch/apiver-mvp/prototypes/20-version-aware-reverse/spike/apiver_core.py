"""
PROTOTYPE plumbing for GitHub ticket #20 (intra-version hyperlinking) — not the real
apiver design.

Extends the 05 spike's minimal composition mechanism with the thing under test: a
**mount-time wrapper that stamps the serving Version onto the request**, plus a
version-aware `reverse()` and a hyperlink field built on it.

The question being answered: can a view inherited from V1 into V2 produce V2-rooted
URLs without V2 redeclaring anything?
"""

from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any

from django.urls import NoReverseMatch, path
from rest_framework import serializers
from rest_framework.reverse import reverse as drf_reverse
from rest_framework.routers import SimpleRouter


#: The Version serving the current request, for code that has no request to consult —
#: a bare `reverse()`, a model's `get_absolute_url()`. Set and reset by the mount-time
#: wrapper. A ContextVar rather than a threadlocal so it is correct under async too.
current_version: ContextVar = ContextVar("apiver_current_version", default=None)

#: Which Alias out-of-band code links against when there is no request and no context —
#: stands in for a Django setting in the real library. `None` reproduces the old
#: behaviour of silently falling back to the Base Version.
out_of_band_alias: str | None = None


@dataclass
class Registration:
    kind: str  # "viewset" | "view"
    key: str
    handler: Any
    basename: str | None = None
    url_path: str | None = None
    name: str | None = None


def _stamp_version(callback, version):
    """Wrap a resolved callback so the Version serving this request is on the request.

    This is the same mount-time seam ticket 12 already chose for deprecation/sunset
    headers — it closes directly over the Version object rather than reverse-engineering
    which Version served a request from `resolver_match`, which cannot work for the
    unnamespaced Base Version.

    The wrapper must stay transparent to DRF introspection: `callback.cls`,
    `.initkwargs` and `.actions` are what apiver's own route identity (ADR 0001) and
    drf-spectacular both read. `functools.wraps` copies `__dict__`, which is where DRF
    puts them — asserted in the tests rather than assumed.
    """

    @wraps(callback)
    def wrapper(request, *args, **kwargs):
        request.apiver_version = version
        token = current_version.set(version)
        try:
            return callback(request, *args, **kwargs)
        finally:
            current_version.reset(token)

    return wrapper


class Version:
    def __init__(self, name: str, parent: "Version | None" = None):
        self.name = name
        self.parent = parent
        self._registrations: dict[str, Registration] = {}
        self._removed: set[str] = set()
        self._urlpatterns_cache: list | None = None

    # -- authoring -------------------------------------------------------------

    def derive(self, name: str) -> "Version":
        return Version(name, parent=self)

    def register_viewset(self, key: str, viewset, *, basename: str | None = None) -> "Version":
        # The literal "decorate the view from register()" proposal, implemented so the
        # tests can show what it does. It stamps the *class*, once, at authoring time —
        # and a class registered in V1 is the same object V2 inherits, so this can only
        # ever report the version that registered it, never the version serving.
        viewset.stamped_at_register = self.name
        self._registrations[key] = Registration(
            kind="viewset", key=key, handler=viewset, basename=basename or key
        )
        return self

    def register_view(self, key: str, view, *, url_path: str, name: str) -> "Version":
        self._registrations[key] = Registration(
            kind="view", key=key, handler=view, url_path=url_path, name=name
        )
        return self

    def remove(self, key: str) -> "Version":
        self._removed.add(key)
        return self

    # -- composition -----------------------------------------------------------

    @property
    def is_base(self) -> bool:
        return self.parent is None

    @property
    def namespace(self) -> str | None:
        """Base Version keeps bare URL names; authored Versions are namespaced (ADR 0001)."""
        return None if self.is_base else self.name

    def resolution_table(self) -> dict[str, Registration]:
        table: dict[str, Registration] = {}
        if self.parent is not None:
            table.update(self.parent.resolution_table())
        for key in self._removed:
            table.pop(key, None)
        table.update(self._registrations)
        return table

    def urlpatterns(self) -> list:
        """Build urlpatterns, every callback wrapped so it carries this Version.

        Cached, so an Alias mounting this Version reuses the *exact same* callback
        objects rather than rebuilding them (ADR 0002 item 8).
        """
        if self._urlpatterns_cache is not None:
            return self._urlpatterns_cache

        table = self.resolution_table()
        router = SimpleRouter()
        view_patterns = []
        for reg in table.values():
            if reg.kind == "viewset":
                router.register(reg.key, reg.handler, basename=reg.basename)
            else:
                view_patterns.append(path(reg.url_path, reg.handler.as_view(), name=reg.name))

        # Explicit view patterns before router patterns — load-bearing, per 05.
        patterns = view_patterns + router.urls
        for pattern in patterns:
            pattern.callback = _stamp_version(pattern.callback, self)

        self._urlpatterns_cache = patterns
        return patterns

    @property
    def urls(self):
        """What `include()` needs. Base is bare; authored carries an app_name."""
        if self.is_base:
            return self.urlpatterns()
        return (self.urlpatterns(), self.name)


class Alias:
    """A movable name pointing at a Version, mounted by reusing its exact callbacks."""

    def __init__(self, name: str, *, target: Version):
        self.name = name
        self.target = target

    @property
    def urls(self):
        # app_name is the *target's*; the instance namespace is the alias's own,
        # supplied by the caller via include(..., namespace=alias.name).
        return (self.target.urlpatterns(), self.target.name)


# -- version-aware reversing ---------------------------------------------------


def namespace_for(request) -> str | None:
    """Which URL namespace should a link generated during this request use?

    Two sources, deliberately in this order:

    1. `resolver_match.namespace` — the *instance* namespace actually matched. This is
       what makes an Alias work: a request that came in via `/api/stable/` keeps
       producing stable-rooted links rather than leaking the concrete version name.
    2. the stamped Version — the fallback, and the only source that can also answer
       "*which Version object* is serving this?", which reverse() doesn't need but
       version-conditional view/serializer logic does.
    """
    if request is not None:
        match = getattr(request, "resolver_match", None)
        if match is not None and match.namespace:
            return match.namespace
        version = getattr(request, "apiver_version", None)
        if version is not None:
            return version.namespace

    # No request, but inside one (a bare reverse(), a get_absolute_url()).
    version = current_version.get()
    if version is not None:
        return version.namespace

    # Genuinely out of band: a Celery task, a management command, a cron job. Falling
    # back to the Base Version points at the *oldest* API — the first one to be sunset.
    # An Alias is the better target: it moves as versions are promoted, so out-of-band
    # code never needs editing when a version ships or retires.
    return out_of_band_alias


def apiver_reverse(viewname, *, request=None, args=None, kwargs=None, format=None, **extra):
    """Version-aware `reverse()`, usable as a drop-in for Django's and DRF's.

    Falls back to the bare name when the versioned one doesn't resolve, so that a project
    which replaced *every* `reverse()` call — including ones pointing at the admin, a
    health check or a login page — keeps working. Without this, blind prefixing turns
    every unversioned URL into a `NoReverseMatch` the moment a versioned request is being
    served.
    """
    namespace = namespace_for(request)
    if namespace:
        try:
            return drf_reverse(
                f"{namespace}:{viewname}",
                args=args,
                kwargs=kwargs,
                request=request,
                format=format,
                **extra,
            )
        except NoReverseMatch:
            pass  # not a route of this Version — fall through to the bare name
    return drf_reverse(
        viewname, args=args, kwargs=kwargs, request=request, format=format, **extra
    )


class VersionedHyperlinkedIdentityField(serializers.HyperlinkedIdentityField):
    """A HyperlinkedIdentityField that resolves within the Version serving the request."""

    def get_url(self, obj, view_name, request, format):
        if hasattr(obj, "pk") and obj.pk is None:
            return None
        lookup_value = getattr(obj, self.lookup_field)
        kwargs = {self.lookup_url_kwarg: lookup_value}
        return apiver_reverse(view_name, kwargs=kwargs, request=request, format=format)
