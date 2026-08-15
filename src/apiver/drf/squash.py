"""`apiver squash` (ticket #77, ADR 0009): make a version's own `registry.py`
an explicit, complete list of every route it resolves — including whatever
it only ever inherited implicitly from further up the chain — without
touching its parent link.

Operates on `registry.py` files only, never on a View or Serializer's source
— ADR 0003's ticket #77 amendment already guarantees a version's root holds
nothing else, so there is no class body to reason about, no LibCST, no
`__mro__` reflection (superseding ADR 0004's original mechanism). Every
absorbed version's root is still re-validated against that same rule here
(ADR 0009 item 3), reusing `checks.py`'s own detection rather than
duplicating it, before anything is written — not because squash itself
deletes anything, but because it's the gate that guarantees a *later*
`apiver remove` can.

The target's parent chain is left exactly as it was: every previously-
implicit route becomes a real `override()` call (a `register()` would raise
— the parent chain still resolves the key), because the parent hasn't gone
anywhere. Squash never deletes anything and never suggests deleting anything
by hand; cutting the parent link, converting these `override()` calls into
`register()`, and dropping the ancestor's mount is `apiver remove`'s job
(ticket #84) — it still never deletes a directory itself, only prints that
one is now safe for `git rm -r`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path

from django.conf import settings

from ..schemes import DEFAULT_SCHEME_NAME, Scheme, UnknownSchemeError, get_scheme
from .checks import _check_no_extra_entries, _check_registry_has_no_inline_definitions
from .init import (
    _grouped_register_lines,
    _prefix_segment,
    _resolve_class_symbol,
    _resolve_function_symbol,
    _resolve_target_dir,
)
from .manifest import ManifestError, load_version, resolve_root_dir
from .version import Registration, Version

__all__ = ["SquashError", "SquashResult", "squash_version"]


class SquashError(RuntimeError):
    """Squash refused to run, or could not produce a flattened registry.py."""


@dataclass
class SquashResult:
    target: str
    registry_path: Path
    #: Ancestors whose implicit routes are now explicit `override()` calls
    #: on the target, oldest first. Their parent link is untouched — they
    #: are still imported, still live, not yet safe to delete (that's
    #: `apiver remove`'s job).
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


def _render_registry(
    target: Version,
    registrations: dict[str, Registration],
    *,
    mount_prefix: str,
    root_dir: str,
) -> str:
    """`target`'s parent link is preserved — every key already resolvable
    through it (`parent._resolved_keys()`) must be re-declared with
    `override()`, never `register()`, since the parent still resolves it
    and `register()` raises on a key that already exists. Only a key
    `target` genuinely introduces itself (no ancestor ever had it) uses
    `register()`.
    """
    assert target.parent is not None
    var_name = target.name
    parent_var = target.parent.name
    parent_keys = target.parent._resolved_keys()
    imports: dict[str, list[str]] = {}
    entries: list[tuple[str, str]] = []
    docs_line: str | None = None
    schema_line: str | None = None
    errors: list[str] = []

    for key, registration in sorted(registrations.items()):
        verb = "override" if key in parent_keys else "register"

        if key == "schema/":
            schema_line = (
                f"{var_name}.{verb}({key!r}, {var_name}.schema_view(prefix={mount_prefix!r}), "
                f"name={registration.name!r})"
            )
            continue
        if key == "docs/":
            docs_line = f"{var_name}.{verb}({key!r}, {var_name}.docs_view(), name={registration.name!r})"
            continue

        handler = registration.handler
        diagnostics: list[str] = []
        handler_cls = getattr(handler, "cls", None)
        if isinstance(handler, type):
            resolved = _resolve_class_symbol(handler, handler, key, diagnostics)
        elif handler_cls is not None:
            resolved = _resolve_class_symbol(handler_cls, handler, key, diagnostics)
        else:
            resolved = _resolve_function_symbol(handler, key, diagnostics)
        if resolved is None:
            errors.extend(diagnostics)
            continue
        module, symbol = resolved
        imports.setdefault(module, []).append(symbol)

        if registration.kind == "viewset":
            line = f"{var_name}.{verb}({key!r}, {symbol}, basename={registration.basename!r})"
        else:
            line = f"{var_name}.{verb}({key!r}, {symbol}, name={registration.name!r})"
        entries.append((_prefix_segment(key), line))

    tail = [line for line in (docs_line, schema_line) if line is not None]
    register_lines = _grouped_register_lines(entries, tail=tail)

    # A key the parent still resolves but target's own resolution_table
    # doesn't means target (or something between it and the parent) removed
    # it. That removal has to be re-declared explicitly too — without it,
    # the freshly-written file would silently resurrect the parent's route,
    # since nothing else in it says the key was ever removed.
    removed_keys = parent_keys - registrations.keys()
    remove_lines = [f"{var_name}.remove({key!r})" for key in sorted(removed_keys)]

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
        f"from {root_dir}.{parent_var}.registry import {parent_var}",
        *([""] + import_lines if import_lines else []),
        "",
        f"{var_name} = {parent_var}.derive({target.name!r})",
        *register_lines,
        *remove_lines,
    ]
    if target.deprecated:
        assert target.sunset_at is not None
        lines.append(f"{var_name}.deprecate(sunset=datetime.fromisoformat({target.sunset_at.isoformat()!r}))")
    if target.frozen:
        lines.append(f"{var_name}.freeze()")
    lines.append("")
    return "\n".join(lines)


def squash_version(name: str) -> SquashResult:
    """Rewrite `name`'s own `registry.py` so every route it resolves —
    including whatever it only ever inherited implicitly — is an explicit
    `override()`/`register()` call, without touching its parent link (ADR
    0009). Refuses — writing nothing — if `name` has no parent (already a
    Base Version), if any absorbed version fails ADR 0003's ticket #77
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
    source = _render_registry(target, registrations, mount_prefix=mount_prefix, root_dir=root_dir)

    registry_path = _resolve_target_dir(f"{root_dir}.{target.name}") / "registry.py"
    registry_path.write_text(source)

    return SquashResult(
        target=target.name,
        registry_path=registry_path,
        absorbed=[ancestor.name for ancestor in reversed(chain)],
    )
