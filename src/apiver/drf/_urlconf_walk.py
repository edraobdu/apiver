"""The recursive URLconf tree walker, shared by `apiver.drf.init` (route
discovery for `apiver init`, ticket 17) and `apiver.drf.manifest` (the
unregistered-route audit, ticket #106).

Neither module owns this walk — `init` classifies what it finds into
`register()` plans, `manifest` only needs the raw set of absolute paths a
live URLconf resolves to — so it lives here instead of being duplicated, or
one importing it from the other and risking a circular import (`init`
already imports `manifest.resolve_root_dir`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.urls import URLPattern, URLResolver
from django.urls.resolvers import LocalePrefixPattern, RegexPattern
from rest_framework.routers import APIRootView

_FORMAT_SUFFIX_RE = re.compile(r"\(\?P<format>|drf_format_suffix")
_MAX_DEPTH = 64


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
    is_regex_declared: bool  # re_path(), not path() — checked by callers that care
    matched_prefix: str  # which of the walk's (non-overlapping) prefixes this fell under


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
                continue  # provably outside every prefix; do not even walk in

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
