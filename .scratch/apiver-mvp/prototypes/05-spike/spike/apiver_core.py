"""
PROTOTYPE plumbing for wayfinder ticket 05 — not the real apiver design.

Minimal delta-composition mechanism, DRF-shaped per the standing decision (no
framework-neutral apiver.core layer). Exists only to let the spike's tests exercise
real DRF routing, reverse(), and drf-spectacular schema generation.
"""

from dataclasses import dataclass
from typing import Any

from django.urls import include, path
from rest_framework.routers import SimpleRouter


@dataclass
class Registration:
    kind: str  # "viewset" | "view"
    key: str
    handler: Any
    basename: str | None = None  # viewset
    url_path: str | None = None  # view
    name: str | None = None  # view


class Version:
    def __init__(self, name: str, parent: "Version | None" = None):
        self.name = name
        self.parent = parent
        self._registrations: dict[str, Registration] = {}
        self._removed: set[str] = set()

    def register_viewset(self, key: str, viewset, *, basename: str | None = None) -> "Version":
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

    def resolution_table(self) -> dict[str, Registration]:
        """Walk the parent chain, apply this version's removals then overrides.

        Whole-registration composition (ADR 0001): a key present in this version's
        own _registrations always replaces the parent's entry wholesale, never merges.
        A key in this version's _removed never resurfaces even if a *grandparent*
        had it and a parent re-added it — removal is evaluated at this version only,
        by design (no un-remove primitive in 0.1).
        """
        table: dict[str, Registration] = {}
        if self.parent is not None:
            table.update(self.parent.resolution_table())
        for key in self._removed:
            table.pop(key, None)
        table.update(self._registrations)
        return table

    def urlpatterns(self) -> list:
        """Build Django urlpatterns from the resolution table.

        Explicit view patterns are placed BEFORE router.urls. DRF's default detail
        route regex (`^<prefix>/(?P<pk>[^/.]+)/$`) is generic enough to swallow a
        sibling path like `payments/summary/` (matching pk="summary") if the router
        patterns are tried first — this ordering is load-bearing, not stylistic.
        """
        table = self.resolution_table()
        # SimpleRouter, not DefaultRouter: DefaultRouter always emits an
        # api-root view plus a format-suffixed twin, even with zero
        # registrations — 2 URL patterns with no corresponding Registration.
        # That breaks the 1:1 correspondence between the resolution table
        # and the resolved urlpatterns that diff/migrate/squash need later.
        router = SimpleRouter()
        view_patterns = []
        for reg in table.values():
            if reg.kind == "viewset":
                router.register(reg.key, reg.handler, basename=reg.basename)
            else:
                view_patterns.append(path(reg.url_path, reg.handler.as_view(), name=reg.name))
        return view_patterns + router.urls
