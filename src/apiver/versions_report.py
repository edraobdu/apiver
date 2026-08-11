"""`apiver versions` (ticket 17): a human-readable summary of the committed
manifest — lineage, frozen status, lifecycle state, alias pointers, and each
version's own routes versus what it inherits (spec items 64-66).

Reads only the already-written `apiver.toml`, never live Version objects —
introspection stays fast and usable in scripts, with no
`DJANGO_SETTINGS_MODULE` or importable project required (ADR 0003 item 8).
Lifecycle state here is therefore a best-effort read of the last committed
snapshot, not the live evaluation gating performs per request (CONTEXT.md:
Sunset) — the same trust gap the manifest already carries everywhere else.

Deliberately outside `apiver.drf`: that package imports `Version`, which
imports drf-spectacular/DRF, which read Django settings at class-definition
time — so merely importing `apiver.drf` requires `DJANGO_SETTINGS_MODULE` to
be set, exactly what `apiver versions` exists to not need. This module (and
`load_committed_manifest`/`MANIFEST_FILENAME` below, which `apiver.drf.manifest`
also imports from here) stays stdlib-only so it stays importable without it.
"""

import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "apiver.toml"


def load_committed_manifest(path: Path) -> dict[str, Any] | None:
    """The manifest currently on disk, or None if there isn't one — a
    missing file is a distinct, equally-stale case from a mismatched one
    (ADR 0003 item 9)."""
    if not path.is_file():
        return None
    return tomllib.loads(path.read_text())


def _lifecycle_state(entry: dict[str, Any], *, now: datetime) -> str:
    """Live, Deprecated, or Sunset (CONTEXT.md) — Archived never appears
    here, since an Archived version has no mount and so never makes it into
    the manifest in the first place (ADR 0003 item 6)."""
    if not entry.get("deprecated"):
        return "live"
    sunset = entry.get("sunset")
    if sunset is not None and datetime.fromisoformat(sunset) <= now:
        return f"sunset (since {sunset})"
    return f"deprecated (sunset {sunset})" if sunset is not None else "deprecated"


def format_versions_report(manifest: dict[str, Any], *, now: datetime | None = None) -> str:
    """Render `manifest` (as loaded from `apiver.toml`) into the text
    `apiver versions` prints. `now` exists for tests to pin the wall clock;
    production always evaluates against the moment the command runs."""
    now = now if now is not None else datetime.now(UTC)
    versions: dict[str, Any] = manifest.get("versions", {})
    aliases: dict[str, str] = manifest.get("aliases", {})

    if not versions:
        return "No versions in the manifest.\n"

    aliases_by_target: dict[str, list[str]] = {}
    for alias_name, target in aliases.items():
        aliases_by_target.setdefault(target, []).append(alias_name)

    lines: list[str] = []
    for name, entry in versions.items():
        parent = entry.get("parent")
        role = "base version" if parent is None else f"derived from {parent}"
        frozen = "frozen" if entry.get("frozen") else "mutable"
        state = _lifecycle_state(entry, now=now)
        lines.append(f"{name} ({role}) — {frozen}, {state}")

        pointers = sorted(aliases_by_target.get(name, []))
        if pointers:
            lines.append(f"  aliases: {', '.join(pointers)}")

        routes: dict[str, Any] = entry.get("routes", {})
        defined = sorted(key for key, route in routes.items() if route.get("source_version") == name)
        inherited_by_source: dict[str, list[str]] = {}
        for key, route in routes.items():
            source = route.get("source_version")
            if source != name:
                inherited_by_source.setdefault(source, []).append(key)
        inherited_count = sum(len(keys) for keys in inherited_by_source.values())

        lines.append(f"  routes: {len(defined)} defined, {inherited_count} inherited")
        for key in defined:
            lines.append(f"    defines:  {key}")
        for source in sorted(inherited_by_source):
            for key in sorted(inherited_by_source[source]):
                lines.append(f"    inherits from {source}: {key}")

        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
