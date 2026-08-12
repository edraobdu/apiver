"""Version Schemes (ticket #66, ADR 0008): validate a Slug's shape, format it
into a Display Name, and order Slugs chronologically — the one project-wide
convention `APIVER_VERSION_SCHEME` names (CONTEXT.md: Scheme).

Stdlib-only, on purpose: `apiver versions` (`versions_report.py`) reads only
the committed manifest, with no Django settings and no importable project,
and still needs a Scheme to sort/format what it reads. Importing anything
from `apiver.drf` here would drag in DRF/drf-spectacular, which read Django
settings at import time, and break that guarantee.

A Slug is either a Scheme's own base grammar (`v1`, `v1_2_3`, `d2026_08_11`)
or that same base with a trailing Label (`v1_testing`, `v1_2_3_testing`,
`d2026_08_11_testing` — ADR item 4), a uniform grammar across every Scheme
giving branch/testing names a legal shape without making them a chronological
point: a Label-suffixed Slug formats with a `-` before the Label and sorts
alongside its base point rather than into the timeline (`compare()` below).
"""

import re
from abc import ABC, abstractmethod

_LABEL_RE = re.compile(r"^(?P<base>.+)_(?P<label>[a-z][a-z0-9]*)$")


class UnknownSchemeError(ValueError):
    """`APIVER_VERSION_SCHEME` (or an explicit scheme name) doesn't name one
    of the three built-in Schemes (ADR 0008 item 3)."""


class Scheme(ABC):
    """One project's version-naming convention (CONTEXT.md: Scheme, ADR
    0008 item 2).

    The Label grammar (ADR item 4) is uniform across every Scheme and lives
    here, in the base class — only what actually varies by Scheme (a Slug's
    own base shape, its Display Name, its chronological sort key) is left to
    subclasses via `_base_pattern`, `_format_base`, and `_sort_key`.
    """

    name: str
    _base_pattern: re.Pattern[str]

    def _split_label(self, slug: str) -> tuple[str, str | None]:
        match = _LABEL_RE.match(slug)
        if match and self._base_pattern.fullmatch(match.group("base")):
            return match.group("base"), match.group("label")
        return slug, None

    def validate(self, slug: str) -> bool:
        base, _ = self._split_label(slug)
        return bool(self._base_pattern.fullmatch(base))

    def format(self, slug: str) -> str:
        base, label = self._split_label(slug)
        if not self._base_pattern.fullmatch(base):
            raise ValueError(f"{slug!r} does not conform to the {self.name!r} scheme.")
        display = self._format_base(base)
        return f"{display}-{label}" if label is not None else display

    def compare(self, slug_a: str, slug_b: str) -> int:
        """-1/0/1, chronological order within this Scheme (ADR item 2).

        A Label-suffixed Slug carries no chronological point of its own — it
        sorts alongside its base (same sort key as the un-suffixed form), a
        bare base breaking the tie ahead of its own Label variant, and two
        Label variants of the same base breaking the tie alphabetically
        purely for a deterministic total order (ADR items 4/6).
        """
        if slug_a == slug_b:
            return 0
        base_a, label_a = self._split_label(slug_a)
        base_b, label_b = self._split_label(slug_b)
        key_a, key_b = self._sort_key(base_a), self._sort_key(base_b)
        if key_a != key_b:
            return -1 if key_a < key_b else 1
        if label_a is None:
            return -1
        if label_b is None:
            return 1
        return -1 if slug_a < slug_b else 1

    @abstractmethod
    def _format_base(self, base: str) -> str: ...

    @abstractmethod
    def _sort_key(self, base: str) -> tuple[int, ...]: ...


class _Sequential(Scheme):
    name = "sequential"
    _base_pattern = re.compile(r"^v(?P<n>\d+)$")

    def _format_base(self, base: str) -> str:
        return base

    def _sort_key(self, base: str) -> tuple[int, ...]:
        match = self._base_pattern.fullmatch(base)
        assert match is not None
        return (int(match["n"]),)


class _Semver(Scheme):
    name = "semver"
    _base_pattern = re.compile(r"^v(?P<major>\d+)_(?P<minor>\d+)_(?P<patch>\d+)$")

    def _format_base(self, base: str) -> str:
        match = self._base_pattern.fullmatch(base)
        assert match is not None
        return f"v{match['major']}.{match['minor']}.{match['patch']}"

    def _sort_key(self, base: str) -> tuple[int, ...]:
        match = self._base_pattern.fullmatch(base)
        assert match is not None
        return (int(match["major"]), int(match["minor"]), int(match["patch"]))


class _Date(Scheme):
    name = "date"
    _base_pattern = re.compile(r"^d(?P<year>\d{4})_(?P<month>\d{2})_(?P<day>\d{2})$")

    def _format_base(self, base: str) -> str:
        match = self._base_pattern.fullmatch(base)
        assert match is not None
        return f"{match['year']}-{match['month']}-{match['day']}"

    def _sort_key(self, base: str) -> tuple[int, ...]:
        match = self._base_pattern.fullmatch(base)
        assert match is not None
        return (int(match["year"]), int(match["month"]), int(match["day"]))


SEQUENTIAL = _Sequential()
SEMVER = _Semver()
DATE = _Date()

#: Unset `APIVER_VERSION_SCHEME` defaults here — today's `v1`/`v2` behavior,
#: unchanged (ADR 0008 Consequences' zero-migration guarantee).
DEFAULT_SCHEME_NAME = "sequential"

_SCHEMES: dict[str, Scheme] = {scheme.name: scheme for scheme in (SEQUENTIAL, SEMVER, DATE)}
SCHEME_NAMES: tuple[str, ...] = tuple(_SCHEMES)


def get_scheme(name: str) -> Scheme:
    try:
        return _SCHEMES[name]
    except KeyError:
        raise UnknownSchemeError(
            f"{name!r} is not a recognized APIVER_VERSION_SCHEME — expected one of "
            f"{', '.join(sorted(SCHEME_NAMES))} (ADR 0008 item 3)."
        ) from None
