"""The directory-shape system check (ticket 15, ADR 0003 items 1-3, ADR 0007
items 3-5; unified across Base and Authored Versions by the ticket #73
amendment to ADR 0003).

Layout enforcement is split across two mechanisms on purpose (ADR 0003 item
2): version-suffixed class names are checked at `register()`/`override()`
time in `version.py`, because that call already holds the class object.
Directory shape has no equivalent moment — nothing at import time reveals
which file a `register()` call was made from short of walking the caller's
stack frame — so it runs instead as an ordinary Django system check, which
`manage.py check`/CI already run without apiver asking for anything special.

A project names its versions via two settings — `APIVER_ROOT_DIR` (the
dotted path to the package holding every version) and `APIVER_VERSIONS` (a
plain list of Live names) — and each version's directory is *derived* as
`f"{APIVER_ROOT_DIR}.{name}"` rather than independently declared (ADR 0007
item 4): a mis-named directory isn't flagged by this check, it's invisible,
because nothing ever derives a path to it in the first place.

Every version's root — Base or Authored, no distinction — is only required
to contain `registry.py`. `serializers.py`/`views.py`, and any other
implementation code, stay wherever the project already put them (ADR 0003
item 3): apiver enforces where routing is declared, never where the rest of
the code lives, so this check has no need to know which configured version
is the base.
"""

from importlib import import_module
from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Warning, register

from ..schemes import DEFAULT_SCHEME_NAME, SCHEME_NAMES
from .manifest import ManifestError, _load_aliases, _load_versions, manifest_diff

REQUIRED_FILES = ("registry.py",)

# ADR 0004 item 8: the endless-chain worry central to why deltas-forward was
# chosen over the inverse architecture needs an actual mechanism, not a
# paragraph nobody reads.
DEFAULT_MAX_LIVE_VERSIONS = 3


@register()
def check_version_layout(app_configs=None, **kwargs) -> list[Error]:
    version_names: list[str] = getattr(settings, "APIVER_VERSIONS", [])
    if not version_names:
        return []

    root_dir: str | None = getattr(settings, "APIVER_ROOT_DIR", None)
    if not root_dir:
        return [
            Error(
                "apiver needs APIVER_ROOT_DIR set to derive each version's package path from "
                "APIVER_VERSIONS's names — without it, this check has nothing to check "
                "(ADR 0007 item 3).",
                id="apiver.E006",
            )
        ]

    messages: list[Error] = []
    for name in version_names:
        messages.extend(_check_root(name, f"{root_dir}.{name}"))
    return messages


def _check_root(name: str, module_path: str) -> list[Error]:
    try:
        module = import_module(module_path)
    except ImportError as exc:
        return [
            Error(
                f"version {name!r}'s root {module_path!r} could not be imported: {exc}",
                id="apiver.E001",
            )
        ]

    root_dir = getattr(module, "__path__", None)
    if root_dir is None:
        return [
            Error(
                f"version {name!r}'s root {module_path!r} is a module, not a package — "
                "a version root must be a package directory (ADR 0003 item 1).",
                id="apiver.E001",
            )
        ]
    root_dir = Path(next(iter(root_dir)))

    return [
        Error(
            f"version {name!r}'s root {module_path!r} is missing {filename!r}",
            id="apiver.E002",
        )
        for filename in REQUIRED_FILES
        if not (root_dir / filename).is_file()
    ]


@register()
def check_manifest_freshness(app_configs=None, **kwargs) -> list[Error | Warning]:
    """Nags locally, at Warning level, when `apiver.toml` doesn't match the
    live Version objects (ticket 16, ADR 0003 item 9) — the same idiom as
    `makemigrations --check --dry-run`, but firing on nearly every
    `manage.py` invocation instead of only a CI step that remembers to ask.

    Warning, not Error: the running server never reads the manifest (ADR
    0003 item 8), so a stale file breaks nothing live and blocking
    `runserver` over it would enforce more than the check needs. A project
    wanting a hard local gate already has `manage.py check --fail-level
    WARNING`.

    A no-op when `APIVER_VERSIONS` isn't configured — a project that hasn't
    adopted the manifest yet has nothing for this check to compare against.
    """
    if not getattr(settings, "APIVER_VERSIONS", None):
        return []

    try:
        resolved, current, committed = manifest_diff()
    except ManifestError as exc:
        return [Error(f"apiver.toml could not be generated: {exc}", id="apiver.E004")]

    if committed != current:
        return [
            Warning(
                f"{resolved} is stale or missing — run `apiver manifest` to regenerate it.",
                id="apiver.W001",
            )
        ]
    return []


@register()
def check_alias_registration(app_configs=None, **kwargs) -> list[Error]:
    """For each `APIVER_ALIASES` entry, verifies the derived path
    (`f"{APIVER_ROOT_DIR}.urls.{name}"`) imports and is an `Alias` instance
    — the same guarantee `check_version_layout` already gives a
    misconfigured `APIVER_VERSIONS` entry (ticket #53).

    A no-op when `APIVER_ALIASES` isn't configured — an alias is optional,
    default `[]` (ADR 0007's second amendment).
    """
    if not getattr(settings, "APIVER_ALIASES", None):
        return []

    try:
        _load_aliases()
    except ManifestError as exc:
        return [Error(f"apiver could not resolve APIVER_ALIASES: {exc}", id="apiver.E008")]
    return []


@register()
def check_max_live_versions(app_configs=None, **kwargs) -> list[Error | Warning]:
    """Warns when the number of Live Versions exceeds `APIVER_MAX_LIVE_VERSIONS`
    (default 3) — ticket 19, ADR 0004 item 8.

    Counted off `APIVER_VERSIONS`, the live `Version` registry, never the
    manifest (ADR 0004 item 8's "code is authoritative" principle): every
    entry is imported fresh and is, by construction, mounted in the URLconf
    (`apiver.drf.manifest`'s docstring), which is exactly what makes a
    Version Live — including while Deprecated or past Sunset, since a Sunset
    Version still needs its mount to answer 410. A Version only stops
    counting once its mount, and so its `APIVER_VERSIONS` entry, is removed
    (Archived). `Frozen` is a mutability state unrelated to whether a
    Version is served, so it plays no part in this count.

    Warning, not Error: nothing about serving a request breaks at four live
    versions, so this is a maintenance-burden signal, not a correctness one.
    A project wanting a hard gate already has `manage.py check --fail-level
    WARNING` — no new apiver escalation mechanism.

    A no-op when `APIVER_VERSIONS` isn't configured, the same convention
    `check_manifest_freshness` uses — a project that hasn't adopted the
    manifest settings yet has nothing for this check to count.
    """
    if not getattr(settings, "APIVER_VERSIONS", None):
        return []

    try:
        versions = _load_versions()
    except ManifestError as exc:
        return [Error(f"apiver could not count Live Versions: {exc}", id="apiver.E005")]

    max_live = getattr(settings, "APIVER_MAX_LIVE_VERSIONS", DEFAULT_MAX_LIVE_VERSIONS)
    live_count = len(versions)
    if live_count <= max_live:
        return []

    return [
        Warning(
            f"{live_count} Live Versions are mounted ({', '.join(sorted(versions))}), "
            f"exceeding APIVER_MAX_LIVE_VERSIONS={max_live}. Consider `apiver squash` or "
            "rebasing onto a fresh base version (ADR 0004 item 8).",
            id="apiver.W002",
        )
    ]


@register()
def check_version_scheme(app_configs=None, **kwargs) -> list[Error]:
    """Validates `APIVER_VERSION_SCHEME` names one of apiver's three
    built-in Schemes (ticket #66, ADR 0008 item 3) — the same
    settings-validation idiom `check_version_layout` already applies to
    `APIVER_ROOT_DIR`. A misspelled value fails loud here rather than
    surfacing later as a confusing slug-formatting or sort-order bug in
    `apiver manifest`/`apiver versions`.

    Unset is not an error: it defaults to `sequential` (ADR 0008
    Consequences' zero-migration guarantee), one of the very values this
    check accepts.
    """
    scheme_name = getattr(settings, "APIVER_VERSION_SCHEME", DEFAULT_SCHEME_NAME)
    if scheme_name in SCHEME_NAMES:
        return []
    return [
        Error(
            f"APIVER_VERSION_SCHEME={scheme_name!r} is not a recognized value — expected one of "
            f"{', '.join(sorted(SCHEME_NAMES))} (ADR 0008 item 3).",
            id="apiver.E009",
        )
    ]
