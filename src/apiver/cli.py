"""apiver's command-line entry point (tickets 16-17, 43, 54).

A standalone script, not a `manage.py` subcommand, so offline tooling can
introspect a project without importing the whole thing (spec item 66).
`manifest`, `init`, `mount`, and `alias` still need
`DJANGO_SETTINGS_MODULE` resolved, exactly as any other Django-adjacent CLI
(celery, gunicorn) requires, since they build from live `Version`/`Alias`
objects that only exist once Django settings are configured. Ticket #54
adds two alternatives to exporting the env var yourself, mirroring
pytest-django's own `--ds` precedence: a top-level `--settings` flag, then
the env var, then `[tool.apiver].django_settings_module` in
`./pyproject.toml`. `versions` is the exception: it reads only the
already-written `apiver.toml` off disk, so it needs neither Django settings
nor an importable project — its imports are therefore kept out of this
module's top level and loaded inside its own command function, so merely
invoking `apiver versions` never pulls in `apiver.drf` (which imports DRF/
drf-spectacular, and those read Django settings at import time).

Ticket #54 also drops the matching `PYTHONPATH=.` requirement: `manage.py`
gets the project root on `sys.path` for free (Python adds a
directly-executed script's own directory, and `manage.py` is invoked from
the project root), but the `apiver` entry point is installed into
`.venv/bin` and gets no such trick — so `main()` puts the current working
directory on `sys.path` itself, the same "project root" `pyproject.toml`
resolution already assumes.
"""

import argparse
import os
import sys
import tomllib
from pathlib import Path

from .versions_report import MANIFEST_FILENAME, format_versions_report, load_committed_manifest


def _resolve_django_settings_module(settings_flag: str | None) -> str | None:
    """flag -> env var -> `[tool.apiver].django_settings_module` in
    `./pyproject.toml` (ticket #54), mirroring pytest-django's own `--ds`
    precedence. `pyproject.toml` is resolved relative to the current
    working directory only, matching how `apiver.toml`/`manifest_path` are
    already resolved — no upward directory search."""
    if settings_flag:
        return settings_flag

    env_value = os.environ.get("DJANGO_SETTINGS_MODULE")
    if env_value:
        return env_value

    pyproject_path = Path.cwd() / "pyproject.toml"
    if not pyproject_path.is_file():
        return None
    data = tomllib.loads(pyproject_path.read_text())
    value = data.get("tool", {}).get("apiver", {}).get("django_settings_module")
    return value if isinstance(value, str) else None


def _cmd_init(*, prefix: str | None, manifest_path: str | None) -> int:
    from .drf.init import InitError, write_init

    try:
        registry_path, aggregation_path = write_init(prefix=prefix)
    except InitError as exc:
        print(f"apiver: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {registry_path}")
    print(f"wrote {aggregation_path}")
    # Folded into init for the base version (ADR 0003 item 7) — the
    # newly-written registry.py is what APIVER_VERSIONS must already point
    # at for this to succeed; a registration in settings has to precede
    # the file existing, exactly as `apiver manifest` already requires.
    return _cmd_manifest(check=False, path=manifest_path)


def _cmd_mount(*, version_name: str, from_version: str) -> int:
    from .drf.init import InitError, write_mount

    try:
        registry_path, aggregation_path = write_mount(version_name, from_version=from_version)
    except InitError as exc:
        print(f"apiver: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {registry_path}")
    print(f"wrote {aggregation_path}")
    # Unlike init (folded into APIVER_VERSIONS ahead of the base
    # version's registry.py existing), mount has nothing to check this
    # against — the new version isn't live yet, so a forgotten settings
    # edit fails silently at request time rather than here.
    print(f"apiver: add {version_name!r} to APIVER_VERSIONS to make it live.")
    return 0


def _cmd_alias(*, name: str, from_version: str) -> int:
    from .drf.init import InitError, write_alias

    try:
        aggregation_path = write_alias(name, from_version=from_version)
    except InitError as exc:
        print(f"apiver: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {aggregation_path}")
    # Same posture as mount: nothing to check this against yet — the alias
    # isn't live until a developer adds it to APIVER_ALIASES by hand.
    print(f"apiver: add {name!r} to APIVER_ALIASES to make it live.")
    return 0


def _cmd_manifest(*, check: bool, path: str | None) -> int:
    import tomli_w

    from .drf.manifest import ManifestError, manifest_diff

    try:
        resolved, current, committed = manifest_diff(path)
    except ManifestError as exc:
        print(f"apiver: {exc}", file=sys.stderr)
        return 1

    if check:
        if committed is None:
            print(
                f"apiver: {resolved} does not exist — run `apiver manifest` to generate it.",
                file=sys.stderr,
            )
            return 1
        if committed != current:
            print(
                f"apiver: {resolved} is stale — run `apiver manifest` to regenerate it.",
                file=sys.stderr,
            )
            return 1
        print(f"{resolved} is up to date.")
        return 0

    resolved.write_text(tomli_w.dumps(current))
    print(f"wrote {resolved}")
    return 0


def _cmd_versions(*, path: str | None) -> int:
    resolved = Path(path) if path is not None else Path.cwd() / MANIFEST_FILENAME
    manifest = load_committed_manifest(resolved)
    if manifest is None:
        print(
            f"apiver: {resolved} does not exist — run `apiver manifest` to generate it.",
            file=sys.stderr,
        )
        return 1

    print(format_versions_report(manifest), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apiver")
    parser.add_argument(
        "--settings",
        default=None,
        help="DJANGO_SETTINGS_MODULE to use, pytest-django `--ds`-style — takes precedence over the "
        "env var and pyproject.toml's [tool.apiver].django_settings_module. Unused by `versions`.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser(
        "manifest",
        help="Write apiver.toml, a committed snapshot of the live resolution tables.",
    )
    manifest_parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if apiver.toml is stale or missing, without writing it.",
    )
    manifest_parser.add_argument(
        "--path",
        default=None,
        help="Where to read/write apiver.toml (default: ./apiver.toml).",
    )

    init_parser = subparsers.add_parser(
        "init",
        help="Start the base version: adopt an existing project's routes under --prefix if there are "
        "any, or scaffold a route-less one if there aren't — generating registry.py and the "
        "manifest, moving nothing.",
    )
    init_parser.add_argument(
        "--prefix",
        default=None,
        help="Only routes under this absolute path are adopted (e.g. api/) — excludes admin/, "
        "third-party auth urls, and anything else outside the API surface. Defaults to "
        "APIVER_ROOT_PREFIX when unset.",
    )
    init_parser.add_argument(
        "--manifest-path",
        default=None,
        help="Where to write apiver.toml (default: ./apiver.toml).",
    )

    mount_parser = subparsers.add_parser(
        "mount",
        help="Author a new version: generate its registry.py from scratch, derived from --from, with "
        "its own schema/docs routes already wired, then append its include() to "
        "<APIVER_ROOT_DIR>/urls.py.",
    )
    mount_parser.add_argument(
        "version",
        help="The new version's name (e.g. v2) — mount creates <APIVER_ROOT_DIR>.<version>.registry "
        "from scratch; refuses if it already exists.",
    )
    mount_parser.add_argument(
        "--from",
        dest="from_version",
        required=True,
        help="The version to derive the new version from (e.g. v1) — its registry.py must already "
        "exist at <APIVER_ROOT_DIR>.<from>.registry.",
    )

    alias_parser = subparsers.add_parser(
        "alias",
        help="Declare a new Alias pointing at an already-mounted version, appended straight into the "
        "Aggregation Root — its conventional home. No registry.py, no schema/docs wiring of its own.",
    )
    alias_parser.add_argument(
        "name",
        help="The alias's name (e.g. stable) — becomes the module-level variable name appended to "
        "<APIVER_ROOT_DIR>/urls.py; refuses if it collides with anything already mounted there.",
    )
    alias_parser.add_argument(
        "--from",
        dest="from_version",
        required=True,
        help="The version to point the alias at (e.g. v2) — must already be mounted in the Aggregation Root.",
    )

    versions_parser = subparsers.add_parser(
        "versions",
        help="Print lineage, frozen status, lifecycle state, alias pointers and route composition "
        "from apiver.toml, without booting the project.",
    )
    versions_parser.add_argument(
        "--path",
        default=None,
        help="Where to read apiver.toml (default: ./apiver.toml).",
    )

    args = parser.parse_args(argv)

    # The project root apiver.toml/pyproject.toml resolution already assumes
    # (cwd) — put on sys.path so `--settings`/env var/pyproject.toml values
    # naming project-local modules (e.g. `config.settings`) actually import,
    # without a developer having to export PYTHONPATH=. themselves.
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    # `versions` reads only the committed manifest (spec item 66) — the only
    # apiver command that works without DJANGO_SETTINGS_MODULE set.
    if args.command == "versions":
        return _cmd_versions(path=args.path)

    resolved_settings = _resolve_django_settings_module(args.settings)
    if not resolved_settings:
        print("apiver: DJANGO_SETTINGS_MODULE is not set.", file=sys.stderr)
        return 1
    os.environ["DJANGO_SETTINGS_MODULE"] = resolved_settings

    import django

    django.setup()

    if args.command == "manifest":
        return _cmd_manifest(check=args.check, path=args.path)
    if args.command == "init":
        return _cmd_init(prefix=args.prefix, manifest_path=args.manifest_path)
    if args.command == "mount":
        return _cmd_mount(version_name=args.version, from_version=args.from_version)
    if args.command == "alias":
        return _cmd_alias(name=args.name, from_version=args.from_version)

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
