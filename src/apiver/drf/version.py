from dataclasses import dataclass
from typing import Any

from rest_framework.routers import SimpleRouter


@dataclass(frozen=True)
class Registration:
    """One declaration binding a handler into a Version, keyed by router prefix."""

    prefix: str
    viewset: Any
    basename: str | None


class Version:
    """A named surface of the API, composed from Registrations.

    This is the tracer-bullet slice (ticket 06): a single Version accepting
    ViewSet registrations and producing mountable urls. derive(), override(),
    remove() and freeze() land in later tickets.
    """

    def __init__(self, name: str):
        self.name = name
        self._registrations: dict[str, Registration] = {}

    def register(self, prefix: str, viewset, *, basename: str | None = None) -> "Version":
        self._registrations[prefix] = Registration(prefix, viewset, basename)
        return self

    @property
    def urls(self):
        # Base version (no parent yet): bare URL names, no app_name — ADR 0001
        # item 4. Namespacing only applies to authored Versions, built later.
        router = SimpleRouter()
        for registration in self._registrations.values():
            router.register(registration.prefix, registration.viewset, basename=registration.basename)
        return router.urls, None
