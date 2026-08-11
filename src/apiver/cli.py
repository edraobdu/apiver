"""apiver's command-line entry point (tickets 16-17, 43).

A standalone script, not a `manage.py` subcommand, so offline tooling can
introspect a project without importing the whole thing (spec item 66).
`manifest`, `migrate`, and `mount` still need `DJANGO_SETTINGS_MODULE` set,
exactly as any other Django-adjacent CLI (celery, gunicorn) requires, since
they build from live `Version`/`Alias` objects that only exist once Django
settings are configured. `versions` is the exception: it reads only the
already-written `apiver.toml` off disk, so it needs neither Django settings
nor an importable project — its imports are therefore kept out of this
module's top level and loaded inside its own command function, so merely
invoking `apiver versions` never pulls in `apiver.drf` (which imports DRF/
drf-spectacular, and those read Django settings at import time).
"""

import argparse
import os
import sys
from pathlib import Path

from .versions_report import MANIFEST_FILENAME, format_versions_report, load_committed_manifest


def _cmd_migrate(*, prefix: str | None, manifest_path: str | None) -> int:
    from .drf.migrate import MigrateError, write_registry

    try:
        registry_path, aggregation_path = write_registry(prefix=prefix)
    except MigrateError as exc:
        print(f"apiver: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {registry_path}")
    print(f"wrote {aggregation_path}")
    # Folded into migrate for the base version (ADR 0003 item 7) — the
    # newly-written registry.py is what APIVER_VERSIONS must already point
    # at for this to succeed; a registration in settings has to precede
    # the file existing, exactly as `apiver manifest` already requires.
    return _cmd_manifest(check=False, path=manifest_path)


def _cmd_mount(*, version_name: str, from_version: str) -> int:
    from .drf.migrate import MigrateError, write_mount

    try:
        registry_path, aggregation_path = write_mount(version_name, from_version=from_version)
    except MigrateError as exc:
        print(f"apiver: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {registry_path}")
    print(f"wrote {aggregation_path}")
    # Unlike migrate (folded into APIVER_VERSIONS ahead of the base
    # version's registry.py existing), mount has nothing to check this
    # against — the new version isn't live yet, so a forgotten settings
    # edit fails silently at request time rather than here.
    print(f"apiver: add {version_name!r} to APIVER_VERSIONS to make it live.")
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

    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Adopt an existing project as the base version: generate registry.py and the manifest, "
        "moving nothing.",
    )
    migrate_parser.add_argument(
        "--prefix",
        default=None,
        help="Only routes under this absolute path are adopted (e.g. api/) — excludes admin/, "
        "third-party auth urls, and anything else outside the API surface. Defaults to "
        "APIVER_ROOT_PREFIX when unset.",
    )
    migrate_parser.add_argument(
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

    # `versions` reads only the committed manifest (spec item 66) — the only
    # apiver command that works without DJANGO_SETTINGS_MODULE set.
    if args.command == "versions":
        return _cmd_versions(path=args.path)

    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        print("apiver: DJANGO_SETTINGS_MODULE is not set.", file=sys.stderr)
        return 1

    import django

    django.setup()

    if args.command == "manifest":
        return _cmd_manifest(check=args.check, path=args.path)
    if args.command == "migrate":
        return _cmd_migrate(prefix=args.prefix, manifest_path=args.manifest_path)
    if args.command == "mount":
        return _cmd_mount(version_name=args.version, from_version=args.from_version)

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
