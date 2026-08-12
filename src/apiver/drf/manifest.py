"""apiver.toml: a committed, non-authoritative snapshot of the live
resolution tables (ticket 16, ADR 0003 items 5-9).

Two settings tell apiver which live objects to serialize — there is no
registry to walk yet (that lands with `apiver init`/`apiver versions`,
tickets 17-18), so a project points at its own objects explicitly:

- `APIVER_VERSIONS`: a plain list of Live version names, e.g. `["v1",
  "v2"]`. Each name's `Version` instance is derived as
  `f"{APIVER_ROOT_DIR}.{name}.registry.{name}"` (ADR 0007 items 3-5) —
  typed once, as a name, not twice as a path.
- `APIVER_ALIASES`: a plain list of alias names, e.g. `["stable"]`,
  optional, default `[]`. Each name's `Alias` instance is derived as
  `f"{APIVER_ROOT_DIR}.urls.{name}"` (ADR 0007's second amendment) — an
  alias's conventional home is the Aggregation Root itself, mirroring how
  `APIVER_VERSIONS` derives its own path.
- `APIVER_VERSION_SCHEME`: the project's Scheme name (ticket #66, ADR 0008
  item 2), optional, default `"sequential"`. Declared once, top-level, not
  per version — it names the Scheme every version's Display Name and
  chronological order are derived from.

The manifest mirrors the in-memory resolution table one-to-one (ADR 0003
item 6): per version, parent/frozen/deprecated/sunset/display_name plus
`{route_key: {action, source_version}}`; plus top-level `scheme` and alias
pointers. The running server never reads this file — it exists only for
tooling outside the process (ADR 0003 item 8).
"""

from importlib import import_module
from pathlib import Path
from typing import Any

from django.conf import settings

from ..schemes import DEFAULT_SCHEME_NAME, Scheme, UnknownSchemeError, get_scheme
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
    names: list[str] = getattr(settings, "APIVER_ALIASES", [])
    if not names:
        return {}

    root_dir: str | None = getattr(settings, "APIVER_ROOT_DIR", None)
    if not root_dir:
        raise ManifestError(
            "apiver needs APIVER_ROOT_DIR set to derive each APIVER_ALIASES name's dotted path as "
            "f'{APIVER_ROOT_DIR}.urls.{name}' — without it, there is no live Alias object to read "
            "(ADR 0007's second amendment)."
        )

    aliases: dict[str, Alias] = {}
    for name in names:
        dotted_path = f"{root_dir}.urls.{name}"
        obj = _import_object(dotted_path)
        if not isinstance(obj, Alias):
            raise ManifestError(
                f"{dotted_path!r} (derived from APIVER_ALIASES[{name!r}]) is not an Alias instance."
            )
        aliases[name] = obj
    return aliases


def _configured_scheme() -> tuple[str, Scheme]:
    """The project's `APIVER_VERSION_SCHEME` setting, and the Scheme object
    it names (ticket #66, ADR 0008 item 2) — unset defaults to `sequential`,
    today's behavior, unchanged. An unrecognized name is caught here rather
    than left to surface later as a confusing formatting error, mirroring
    how every other malformed-settings case in this module raises
    ManifestError instead of propagating the underlying exception type."""
    scheme_name = getattr(settings, "APIVER_VERSION_SCHEME", DEFAULT_SCHEME_NAME)
    try:
        return scheme_name, get_scheme(scheme_name)
    except UnknownSchemeError as exc:
        raise ManifestError(str(exc)) from exc


def _version_entry(version: Version, scheme: Scheme) -> dict[str, Any]:
    try:
        display_name = scheme.format(version.name)
    except ValueError as exc:
        raise ManifestError(
            f"version {version.name!r} does not conform to the configured "
            f"APIVER_VERSION_SCHEME={scheme.name!r}: {exc}"
        ) from exc

    entry: dict[str, Any] = {
        "frozen": version.frozen,
        "deprecated": version.deprecated,
        "display_name": display_name,
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

    `scheme` is recorded once, top-level (ADR 0008 item 2: declared per
    project, not per Version) — `apiver versions` (`versions_report.py`)
    reads it back to sort and format without needing Django settings itself.
    """
    versions = _load_versions()
    aliases = _load_aliases()
    scheme_name, scheme = _configured_scheme()
    return {
        "scheme": scheme_name,
        "versions": {name: _version_entry(version, scheme) for name, version in versions.items()},
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
