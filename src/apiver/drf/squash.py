"""`apiver squash` (ticket #77, ADR 0009): flatten a Version's whole ancestor
chain into its own standalone, parentless `registry.py`.

Operates on `registry.py` files only, never on a View or Serializer's source
— ADR 0003's ticket #77 amendment already guarantees a version's root holds
nothing else, so there is no class body to reason about, no LibCST, no
`__mro__` reflection (superseding ADR 0004's original mechanism). Every
absorbed version's root is re-validated against that same rule here (ADR
0009 item 3), reusing `checks.py`'s own detection rather than duplicating
it, before anything is written.

Squash never deletes anything. It rewrites the target's `registry.py` in
place, auto-applied — `git diff` is the review surface (ADR 0009 item 5).
The absorbed versions' directories are left untouched on disk, now safe but
not required to be deleted; that's a separate future `apiver remove`
command's job, not this one's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path

from django.conf import settings

from ..schemes import DEFAULT_SCHEME_NAME, Scheme, UnknownSchemeError, get_scheme
from .checks import _check_no_extra_entries, _check_registry_has_no_inline_definitions
from .init import _resolve_class_symbol, _resolve_function_symbol, _resolve_target_dir
from .manifest import ManifestError, load_version, resolve_root_dir
from .version import Registration, Version

__all__ = ["SquashError", "SquashResult", "squash_version"]


class SquashError(RuntimeError):
    """Squash refused to run, or could not produce a flattened registry.py."""


@dataclass
class SquashResult:
    target: str
    registry_path: Path
    #: Absorbed ancestors, oldest first — left on disk, unreferenced, safe
    #: to delete by hand or with a future `apiver remove` (ADR 0009 item 5).
    absorbed: list[str] = field(default_factory=list)


def _configured_scheme() -> Scheme:
    scheme_name = getattr(settings, "APIVER_VERSION_SCHEME", DEFAULT_SCHEME_NAME)
    try:
        return get_scheme(scheme_name)
    except UnknownSchemeError as exc:
        raise SquashError(str(exc)) from exc


def _ancestor_chain(version: Version) -> list[Version]:
    """Every ancestor of `version`, nearest-parent-first."""
    chain: list[Version] = []
    current = version.parent
    while current is not None:
        chain.append(current)
        current = current.parent
    return chain


def _version_root_dir(name: str, *, root_dir: str) -> Path:
    module_path = f"{root_dir}.{name}"
    try:
        module = import_module(module_path)
    except ImportError as exc:
        raise SquashError(f"version {name!r}'s root {module_path!r} could not be imported: {exc}") from exc
    path = getattr(module, "__path__", None)
    if path is None:
        raise SquashError(
            f"version {name!r}'s root {module_path!r} is a module, not a package — a version root "
            "must be a package directory (ADR 0003 item 1)."
        )
    return Path(next(iter(path)))


def _preflight(chain: list[Version], *, root_dir: str) -> None:
    """Every absorbed version must already satisfy ADR 0003's ticket #77
    rule — reuses `checks.py`'s own detection logic rather than
    duplicating it (ADR 0009 item 3). Every violation across every
    absorbed version is collected and reported together; any violation
    refuses the whole squash, nothing is written."""
    violations: list[str] = []
    for ancestor in chain:
        module_path = f"{root_dir}.{ancestor.name}"
        try:
            version_root = _version_root_dir(ancestor.name, root_dir=root_dir)
        except SquashError as exc:
            violations.append(str(exc))
            continue
        for error in _check_no_extra_entries(ancestor.name, module_path, version_root):
            violations.append(error.msg)
        for error in _check_registry_has_no_inline_definitions(ancestor.name, module_path, version_root):
            violations.append(error.msg)

    if violations:
        raise SquashError(
            "squash refuses to run — every absorbed version must satisfy ADR 0003's ticket #77 rule "
            "(registry.py only, no inline definitions) before it can be safely folded away:\n"
            + "\n".join(f"- {message}" for message in violations)
        )


def _mount_prefix(version_name: str, *, scheme: Scheme) -> str:
    root_prefix = getattr(settings, "APIVER_ROOT_PREFIX", None)
    if root_prefix is None:
        raise SquashError(
            "APIVER_ROOT_PREFIX is not set — apiver doesn't know the absolute URL path this version "
            "mounts under (ADR 0007 item 3)."
        )
    root_prefix = root_prefix.lstrip("/")
    display_name = scheme.format(version_name)
    return root_prefix + f"{display_name}/"


def _registrations_by_key(version: Version) -> dict[str, Registration]:
    seen: dict[str, Registration] = {}
    for route in version.resolution_table.values():
        if route.registration is not None:
            seen[route.registration.key] = route.registration
    return seen


def _render_registry(target: Version, registrations: dict[str, Registration], *, mount_prefix: str) -> str:
    var_name = target.name
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

    if target.deprecated:
        imports.setdefault("datetime", []).append("datetime")

    if errors:
        raise SquashError(
            "squash could not resolve every registration to an importable symbol:\n"
            + "\n".join(f"- {message}" for message in errors)
        )

    import_lines = [
        f"from {module} import {', '.join(sorted(set(symbols)))}"
        for module, symbols in sorted(imports.items())
    ]

    lines = [
        '"""Generated by `apiver squash` (ticket #77, ADR 0009); hand-editable',
        "afterwards, like every other registry.py apiver writes — squash won't",
        "regenerate this file again unless it's run against this version once more.",
        '"""',
        "",
        "from apiver.drf import Version",
        *([""] + import_lines if import_lines else []),
        "",
        f"{var_name} = Version({target.name!r})",
        *register_lines,
    ]
    if target.deprecated:
        assert target.sunset_at is not None
        lines.append(f"{var_name}.deprecate(sunset=datetime.fromisoformat({target.sunset_at.isoformat()!r}))")
    if target.frozen:
        lines.append(f"{var_name}.freeze()")
    lines.append("")
    return "\n".join(lines)


def squash_version(name: str) -> SquashResult:
    """Flatten `name`'s whole ancestor chain into its own `registry.py`
    (ADR 0009). Refuses — writing nothing — if `name` has no parent (already
    a Base Version), if any absorbed version fails ADR 0003's ticket #77
    rule, or if any registration can't be resolved to an importable symbol.
    """
    root_dir = resolve_root_dir()
    try:
        target = load_version(name, root_dir=root_dir)
    except ManifestError as exc:
        raise SquashError(str(exc)) from exc

    chain = _ancestor_chain(target)
    if not chain:
        raise SquashError(
            f"version {name!r} has no parent — it is already a Base Version, nothing to squash."
        )

    _preflight(chain, root_dir=root_dir)

    scheme = _configured_scheme()
    mount_prefix = _mount_prefix(target.name, scheme=scheme)
    registrations = _registrations_by_key(target)
    source = _render_registry(target, registrations, mount_prefix=mount_prefix)

    registry_path = _resolve_target_dir(f"{root_dir}.{target.name}") / "registry.py"
    registry_path.write_text(source)

    return SquashResult(
        target=target.name,
        registry_path=registry_path,
        absorbed=[ancestor.name for ancestor in reversed(chain)],
    )
