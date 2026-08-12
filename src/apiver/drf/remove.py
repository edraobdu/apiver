"""`apiver remove` (ticket #84): the operation that actually moves a version
from Live to **Archived** — the guardrail ADR 0004 item 8 named and squash
(ADR 0009, ticket #77) deliberately left unbuilt. A version is Live, counted,
and mounted through Deprecated and past-Sunset states; it becomes Archived
only once its mount is removed.

Squash makes a descendant's `registry.py` an explicit, complete list of
every route it resolves — including whatever it only ever inherited
implicitly — but deliberately leaves the parent link, the ancestor's
directory, its Aggregation Root mount, and its `APIVER_VERSIONS` entry
untouched (ADR 0009 item 5). `remove` finishes the job for a version named
`VERSION`: every direct child's `.derive(VERSION)` line is cut (turning it
into its own independent Base Version — apiver's model already tolerates
more than one, ADR 0002), `VERSION`'s mount is dropped from the Aggregation
Root, and what's left (its `APIVER_VERSIONS`/`APIVER_BASE_VERSION` entry,
its directory) is printed for a developer to finish by hand.

Hard precondition, checked structurally with the same `resolution_table`/
`_resolved_keys()` machinery squash's own preflight already uses: every
direct child of `VERSION` must already resolve `VERSION`'s entire
contribution explicitly (via a prior `apiver squash`) — not "was squash
run", but "does the child's own resolved-keys set already cover everything
`VERSION` could serve". Any child that doesn't refuses the whole operation,
across every child if `VERSION` branched into more than one descendant —
nothing is written, the same "fail closed, list everything" posture squash
already uses.

`remove` never deletes a directory itself and never edits `settings.py` — an
accidental deletion of source code is a different order of risk than a
rewritten text file, and settings edits stay a hand-edit exactly as `apiver
mount` already treats `APIVER_VERSIONS` for a newly-authored version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from .init import _resolve_class_symbol, _resolve_function_symbol, _resolve_target_dir
from .manifest import ManifestError, load_version, resolve_root_dir
from .squash import _configured_scheme, _mount_prefix, _registrations_by_key
from .version import Registration, Version

__all__ = ["RemoveError", "RemoveResult", "remove_version"]


class RemoveError(RuntimeError):
    """remove refused to run, or could not rewrite every direct child."""


@dataclass
class RemoveResult:
    target: str
    #: Direct children re-parented into their own independent Base
    #: Versions, oldest-registered first — empty if `target` was a leaf
    #: with nothing deriving from it.
    children: list[str] = field(default_factory=list)
    registry_paths: list[Path] = field(default_factory=list)
    aggregation_path: Path = field(default_factory=Path)
    #: True if `target` is (or was) `settings.APIVER_BASE_VERSION` — folded
    #: into the CLI's settings-cleanup hint alongside `APIVER_VERSIONS`.
    was_base_version: bool = False


def _direct_children(target_name: str, *, root_dir: str) -> list[Version]:
    """Every Live version (`APIVER_VERSIONS`) whose immediate parent is
    `target_name` — the population `remove`'s precondition and rewrite both
    operate on. Not a whole-chain walk: only a direct child's own
    `.derive(target_name)` line is ever cut (ADR 0009's "one version at a
    time" choice, mirrored here)."""
    names: list[str] = list(getattr(settings, "APIVER_VERSIONS", []))
    children: list[Version] = []
    for name in names:
        if name == target_name:
            continue
        try:
            version = load_version(name, root_dir=root_dir)
        except ManifestError as exc:
            raise RemoveError(str(exc)) from exc
        if version.parent is not None and version.parent.name == target_name:
            children.append(version)
    return children


def _preflight(target: Version, children: list[Version]) -> None:
    """Every direct child must already explicitly declare (register,
    override, or remove) every key `target` can currently resolve — nothing
    may still be reaching `target` only implicitly, since that link is
    about to be cut. Checked structurally, the same way squash's own
    preflight reuses `checks.py` rather than trusting that squash was in
    fact the tool that last touched the file."""
    target_keys = target._resolved_keys()
    violations: list[str] = []
    for child in children:
        declared = set(child._registrations) | child._removed
        missing = target_keys - declared
        if missing:
            violations.append(
                f"{child.name!r} does not yet explicitly resolve every key {target.name!r} "
                f"contributes — missing {sorted(missing)!r}. Run `apiver squash {child.name}` first."
            )

    if violations:
        raise RemoveError(
            f"remove refuses to run — every direct child of {target.name!r} must already resolve its "
            "entire contribution explicitly (via a prior `apiver squash`) before its mount can be cut:\n"
            + "\n".join(f"- {message}" for message in violations)
        )


def _render_standalone_registry(
    child: Version,
    registrations: dict[str, Registration],
    *,
    mount_prefix: str,
) -> str:
    """Regenerate `child` as its own, parentless Base Version: every key it
    currently resolves — squash already guaranteed (and `_preflight` above
    re-verified) that this is a complete, explicit set — becomes a plain
    `register()` call, since there's no parent left to `override()` against.
    No `remove()` calls either: a key `child` shadowed only ever shadowed
    something the (now-gone) parent chain resolved, so once that chain is
    gone there's nothing left to remove it from.
    """
    var_name = child.name
    imports: dict[str, list[str]] = {}
    register_lines: list[str] = []
    errors: list[str] = []

    for key, registration in sorted(registrations.items(), key=lambda item: (item[0] == "schema/", item[0])):
        if key == "schema/":
            register_lines.append(
                f"{var_name}.register({key!r}, {var_name}.schema_view(prefix={mount_prefix!r}), "
                f"name={registration.name!r})"
            )
            continue
        if key == "docs/":
            register_lines.append(
                f"{var_name}.register({key!r}, {var_name}.docs_view(), name={registration.name!r})"
            )
            continue

        handler = registration.handler
        diagnostics: list[str] = []
        if isinstance(handler, type):
            resolved = _resolve_class_symbol(handler, handler, key, diagnostics)
        else:
            resolved = _resolve_function_symbol(handler, key, diagnostics)
        if resolved is None:
            errors.extend(diagnostics)
            continue
        module, symbol = resolved
        imports.setdefault(module, []).append(symbol)

        if registration.kind == "viewset":
            register_lines.append(
                f"{var_name}.register({key!r}, {symbol}, basename={registration.basename!r})"
            )
        else:
            register_lines.append(f"{var_name}.register({key!r}, {symbol}, name={registration.name!r})")

    if child.deprecated:
        imports.setdefault("datetime", []).append("datetime")

    if errors:
        raise RemoveError(
            f"remove could not resolve every one of {child.name!r}'s registrations to an importable "
            "symbol:\n" + "\n".join(f"- {message}" for message in errors)
        )

    import_lines = [
        f"from {module} import {', '.join(sorted(set(symbols)))}"
        for module, symbols in sorted(imports.items())
    ]

    lines = [
        '"""Regenerated by `apiver remove` (ticket #84); hand-editable',
        f"afterwards, like every other registry.py apiver writes. {var_name!r} is now its own",
        "independent Base Version — its former parent has been archived.",
        '"""',
        "",
        "from apiver.drf import Version",
        *([""] + import_lines if import_lines else []),
        "",
        f"{var_name} = Version({child.name!r})",
        *register_lines,
    ]
    if child.deprecated:
        assert child.sunset_at is not None
        lines.append(f"{var_name}.deprecate(sunset=datetime.fromisoformat({child.sunset_at.isoformat()!r}))")
    if child.frozen:
        lines.append(f"{var_name}.freeze()")
    lines.append("")
    return "\n".join(lines)


def _unmount(target_name: str, *, root_dir: str) -> Path:
    """Drop `target_name`'s import and mount line from the Aggregation
    Root — the exact inverse of `init.py`'s `_write_or_extend_aggregation_root`,
    operating on the identical generated shape. Refuses, writing nothing, if
    that shape has drifted — the same posture the append side already takes
    (`init.py`'s own "has it been hand-edited" refusals)."""
    aggregation_path = _resolve_target_dir(root_dir) / "urls.py"
    if not aggregation_path.is_file():
        raise RemoveError(f"{aggregation_path} does not exist — nothing to unmount {target_name!r} from.")

    source = aggregation_path.read_text()
    lines = source.splitlines()

    import_line = f"from {root_dir}.{target_name}.registry import {target_name}"
    if import_line not in lines:
        raise RemoveError(
            f"{aggregation_path} has no {import_line!r} import — has it been hand-edited into an "
            f"unrecognized shape, or is {target_name!r} not mounted there at all?"
        )
    lines.remove(import_line)

    mount_pattern = re.compile(rf"^\s*path\(.*include\({re.escape(target_name)}\.urls\)\),\s*$")
    mount_indices = [i for i, line in enumerate(lines) if mount_pattern.match(line)]
    if len(mount_indices) != 1:
        raise RemoveError(
            f"{aggregation_path} has {len(mount_indices)} mount line(s) for {target_name!r} — expected "
            "exactly one; has it been hand-edited into an unrecognized shape?"
        )
    del lines[mount_indices[0]]

    aggregation_path.write_text("\n".join(lines) + "\n")
    return aggregation_path


def remove_version(name: str, *, force: bool = False) -> RemoveResult:
    """Archive `name`: cut it out of every direct child's parent chain (each
    becoming its own independent Base Version) and drop its mount from the
    Aggregation Root. Refuses — writing nothing — if any direct child
    doesn't yet explicitly resolve everything `name` contributes, or if
    `name` was never deprecated and `force` isn't passed.

    Never touches `settings.py` and never deletes `name`'s directory —
    both stay hand-edits the caller is told about (ADR 0004 item 8's
    Live/Archived guardrail; `apiver mount`'s identical posture for
    `APIVER_VERSIONS`).
    """
    root_dir = resolve_root_dir()
    try:
        target = load_version(name, root_dir=root_dir)
    except ManifestError as exc:
        raise RemoveError(str(exc)) from exc

    if not target.deprecated and not force:
        raise RemoveError(
            f"version {name!r} was never deprecated — no Deprecation/Sunset headers were ever sent to "
            "callers, so remove refuses to pull its mount out from under live callers without warning. "
            "Deprecate it first (Version.deprecate(sunset=...)), or pass --force to archive it anyway."
        )

    children = _direct_children(name, root_dir=root_dir)
    _preflight(target, children)

    scheme = _configured_scheme()
    rendered: dict[str, str] = {}
    errors: list[str] = []
    for child in children:
        mount_prefix = _mount_prefix(child.name, scheme=scheme)
        try:
            rendered[child.name] = _render_standalone_registry(
                child, _registrations_by_key(child), mount_prefix=mount_prefix
            )
        except RemoveError as exc:
            errors.append(str(exc))
    if errors:
        raise RemoveError("\n".join(errors))

    registry_paths: list[Path] = []
    for child in children:
        registry_path = _resolve_target_dir(f"{root_dir}.{child.name}") / "registry.py"
        registry_path.write_text(rendered[child.name])
        registry_paths.append(registry_path)

    aggregation_path = _unmount(name, root_dir=root_dir)

    return RemoveResult(
        target=name,
        children=[child.name for child in children],
        registry_paths=registry_paths,
        aggregation_path=aggregation_path,
        was_base_version=getattr(settings, "APIVER_BASE_VERSION", None) == name,
    )
