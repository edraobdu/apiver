"""apiver's command-line entry point (ticket 16).

A standalone script, not a `manage.py` subcommand, so offline tooling can
introspect a project without importing the whole thing (spec item 66) — it
still needs `DJANGO_SETTINGS_MODULE` set, exactly as any other
Django-adjacent CLI (celery, gunicorn) requires, since the manifest is built
from live `Version`/`Alias` objects that only exist once Django settings are
configured.
"""

import argparse
import os
import sys


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

    args = parser.parse_args(argv)

    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        print("apiver: DJANGO_SETTINGS_MODULE is not set.", file=sys.stderr)
        return 1

    import django

    django.setup()

    if args.command == "manifest":
        return _cmd_manifest(check=args.check, path=args.path)

    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
