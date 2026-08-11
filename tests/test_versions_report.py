"""Unit tests for the `apiver versions` formatter (ticket 17), independent
of the CLI subprocess seam in test_cli_versions.py — these exercise
format_versions_report() directly against hand-built manifest dicts, the
same shape apiver.toml round-trips through tomllib."""

from datetime import UTC, datetime

from apiver.versions_report import format_versions_report

NOW = datetime(2025, 1, 1, tzinfo=UTC)


def _manifest(**versions):
    return {"versions": versions, "aliases": {}}


def test_reports_no_versions_when_the_manifest_is_empty():
    assert format_versions_report({"versions": {}, "aliases": {}}) == "No versions in the manifest.\n"


def test_base_version_has_no_parent_and_is_live_when_not_deprecated():
    manifest = _manifest(v1={"frozen": True, "deprecated": False, "routes": {}})

    report = format_versions_report(manifest, now=NOW)

    assert "v1 (base version) — frozen, live" in report


def test_derived_version_reports_its_parent_and_mutability():
    manifest = _manifest(v2={"frozen": False, "deprecated": False, "parent": "v1", "routes": {}})

    report = format_versions_report(manifest, now=NOW)

    assert "v2 (derived from v1) — mutable, live" in report


def test_deprecated_version_before_sunset_reports_deprecated_with_the_date():
    manifest = _manifest(
        v2={
            "frozen": False,
            "deprecated": True,
            "parent": "v1",
            "sunset": "2030-01-01T00:00:00+00:00",
            "routes": {},
        }
    )

    report = format_versions_report(manifest, now=NOW)

    assert "deprecated (sunset 2030-01-01T00:00:00+00:00)" in report
    assert "sunset (since" not in report


def test_deprecated_version_past_sunset_reports_sunset_not_deprecated():
    manifest = _manifest(
        v2={
            "frozen": False,
            "deprecated": True,
            "parent": "v1",
            "sunset": "2020-01-01T00:00:00+00:00",
            "routes": {},
        }
    )

    report = format_versions_report(manifest, now=NOW)

    assert "sunset (since 2020-01-01T00:00:00+00:00)" in report


def test_alias_pointers_are_listed_under_their_target_version():
    manifest = {
        "versions": {"v1": {"frozen": True, "deprecated": False, "routes": {}}},
        "aliases": {"stable": "v1", "latest": "v1"},
    }

    report = format_versions_report(manifest, now=NOW)

    assert "aliases: latest, stable" in report


def test_routes_are_split_between_defined_and_inherited():
    manifest = _manifest(
        v1={
            "frozen": True,
            "deprecated": False,
            "routes": {
                "^ping/$": {"source_version": "v1"},
                "^payments/$": {"source_version": "v1"},
            },
        },
        v2={
            "frozen": False,
            "deprecated": False,
            "parent": "v1",
            "routes": {
                "^ping/$": {"source_version": "v1"},
                "^payments/$": {"source_version": "v2"},
            },
        },
    )

    report = format_versions_report(manifest, now=NOW)

    assert "v1 (base version) — frozen, live" in report
    assert "routes: 2 defined, 0 inherited" in report
    assert "v2 (derived from v1) — mutable, live" in report
    assert "routes: 1 defined, 1 inherited" in report
    assert "defines:  ^payments/$" in report
    assert "inherits from v1: ^ping/$" in report


def test_now_defaults_to_the_wall_clock_when_not_given():
    manifest = _manifest(v1={"frozen": True, "deprecated": False, "routes": {}})

    report = format_versions_report(manifest)

    assert "live" in report
