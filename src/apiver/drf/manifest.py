"""apiver.toml: a committed, non-authoritative snapshot of the live
resolution tables (ticket 16, ADR 0003 items 5-9).

Two settings tell apiver which live objects to serialize — there is no
registry to walk yet (that lands with `apiver migrate`/`apiver versions`,
tickets 17-18), so a project points at its own objects explicitly:

- `APIVER_VERSIONS`: a plain list of Live version names, e.g. `["v1",
  "v2"]`. Each name's `Version` instance is derived as
  `f"{APIVER_ROOT_DIR}.{name}.registry.{name}"` (ADR 0007 items 3-5) —
  typed once, as a name, not twice as a path.
- `APIVER_ALIASES`: `{alias_name: "dotted.path.to.Alias instance"}`,
  optional, default `{}`. Unaffected by ADR 0007 — an alias has no fixed
  home the way a version's package does.

The manifest mirrors the in-memory resolution table one-to-one (ADR 0003
item 6): per version, parent/frozen/deprecated/sunset plus
`{route_key: {action, source_version}}`; plus top-level alias pointers. The
running server never reads this file — it exists only for tooling outside
the process (ADR 0003 item 8).
"""

from importlib import import_module
from pathlib import Path
from typing import Any

from django.conf import settings

from ..versions_report import MANIFEST_FILENAME, load_committed_manifest
from .version import Alias, Version

__all__ = [
    "MANIFEST_FILENAME",
    "ManifestError",
    "build_manifest",
    "load_committed_manifest",
    "manifest_diff",
    "manifest_path",
]


class ManifestError(RuntimeError):
    """The manifest could not be built from the configured settings."""


def _import_object(dotted_path: str) -> Any:
    module_path, _, attr = dotted_path.rpartition(".")
    if not module_path:
        raise ManifestError(f"{dotted_path!r} is not a dotted path to an object.")
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise ManifestError(f"{dotted_path!r} could not be imported: {exc}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ManifestError(f"{dotted_path!r} could not be imported: {exc}") from exc


def _load_versions() -> dict[str, Version]:
    names: list[str] = getattr(settings, "APIVER_VERSIONS", [])
    if not names:
        raise ManifestError(
            "APIVER_VERSIONS is empty or unset — apiver has no live Versions to write a "
            "manifest for. Set APIVER_VERSIONS = ['v1', 'v2', ...] in settings."
        )

    root_dir: str | None = getattr(settings, "APIVER_ROOT_DIR", None)
    if not root_dir:
        raise ManifestError(
            "apiver needs APIVER_ROOT_DIR set to derive each APIVER_VERSIONS name's dotted path "
            "as f'{APIVER_ROOT_DIR}.{name}.registry.{name}' — without it, there is no live "
            "Version object to read (ADR 0007 items 3, 5)."
        )

    versions: dict[str, Version] = {}
    for name in names:
        dotted_path = f"{root_dir}.{name}.registry.{name}"
        obj = _import_object(dotted_path)
        if not isinstance(obj, Version):
            raise ManifestError(
                f"{dotted_path!r} (derived from APIVER_VERSIONS[{name!r}]) is not a Version instance."
            )
        versions[name] = obj
    return versions


def _load_aliases() -> dict[str, Alias]:
    configured: dict[str, str] = getattr(settings, "APIVER_ALIASES", {})
    aliases: dict[str, Alias] = {}
    for name, dotted_path in configured.items():
        obj = _import_object(dotted_path)
        if not isinstance(obj, Alias):
            raise ManifestError(f"APIVER_ALIASES[{name!r}] = {dotted_path!r} is not an Alias instance.")
        aliases[name] = obj
    return aliases


def _version_entry(version: Version) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "frozen": version.frozen,
        "deprecated": version.deprecated,
    }
    if version.parent is not None:
        entry["parent"] = version.parent.name
    if version.sunset_at is not None:
        entry["sunset"] = version.sunset_at.isoformat()

    routes: dict[str, Any] = {}
    for route_key, route in version.resolution_table.items():
        routes[route_key] = {
            "action": dict(route.identity.action) if route.identity.action is not None else {},
            "source_version": route.registration.source_version,
        }
    entry["routes"] = routes
    return entry


def build_manifest() -> dict[str, Any]:
    """Serialize every configured live Version and Alias into the manifest
    shape, one-to-one with the in-memory resolution table (ADR 0003 item 6).
    """
    versions = _load_versions()
    aliases = _load_aliases()
    return {
        "versions": {name: _version_entry(version) for name, version in versions.items()},
        "aliases": {name: alias.target.name for name, alias in aliases.items()},
    }


def manifest_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    configured = getattr(settings, "APIVER_MANIFEST_PATH", None)
    if configured is not None:
        return Path(configured)
    return Path.cwd() / MANIFEST_FILENAME


def manifest_diff(path: str | Path | None = None) -> tuple[Path, dict[str, Any], dict[str, Any] | None]:
    """The resolved manifest path, what apiver would write right now, and
    what's currently committed (None if missing)."""
    resolved = manifest_path(path)
    current = build_manifest()
    committed = load_committed_manifest(resolved)
    return resolved, current, committed
