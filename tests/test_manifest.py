import pytest
import tomli_w
from django.core.checks import Error, Warning
from django.core.checks.registry import registry
from django.test import override_settings

from apiver.drf import ManifestError, build_manifest, check_manifest_freshness, check_max_live_versions
from apiver.drf.manifest import load_committed_manifest, manifest_diff, manifest_path
from tests.fixtures_manifest.api.urls import stable
from tests.fixtures_manifest.api.v1.registry import v1
from tests.fixtures_manifest.api.v2.registry import FIXED_SUNSET, v2

ROOT_DIR = "tests.fixtures_manifest.api"


@override_settings(
    APIVER_ROOT_DIR=ROOT_DIR,
    APIVER_VERSIONS=["v1", "v2"],
    APIVER_ALIASES={"stable": "tests.fixtures_manifest.api.urls.stable"},
)
def test_build_manifest_mirrors_the_live_resolution_tables():
    manifest = build_manifest()

    assert manifest["versions"]["v1"]["frozen"] is True
    assert manifest["versions"]["v1"]["deprecated"] is False
    assert "parent" not in manifest["versions"]["v1"]

    assert manifest["versions"]["v2"]["frozen"] is False
    assert manifest["versions"]["v2"]["deprecated"] is True
    assert manifest["versions"]["v2"]["parent"] == "v1"
    assert manifest["versions"]["v2"]["sunset"] == FIXED_SUNSET.isoformat()

    assert manifest["aliases"] == {"stable": "v2"}


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["v1", "v2"])
def test_build_manifest_records_action_and_source_version_per_route():
    manifest = build_manifest()

    v1_routes = manifest["versions"]["v1"]["routes"]
    ping_key = next(key for key, route in v1.resolution_table.items() if route.registration.key == "ping")
    assert v1_routes[ping_key]["source_version"] == "v1"
    assert v1_routes[ping_key]["action"] == {"get": "list"}

    v2_routes = manifest["versions"]["v2"]["routes"]
    # payments is overridden on v2, so its source_version follows the override.
    payments_key = next(
        key for key, route in v2.resolution_table.items() if route.registration.key == "payments"
    )
    assert v2_routes[payments_key]["source_version"] == "v2"
    # ping is untouched by v2's Delta, so it's still traced back to v1.
    inherited_ping_key = next(
        key for key, route in v2.resolution_table.items() if route.registration.key == "ping"
    )
    assert v2_routes[inherited_ping_key]["source_version"] == "v1"


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=[])
def test_no_configured_versions_raises_a_manifest_error():
    with pytest.raises(ManifestError):
        build_manifest()


@override_settings(APIVER_VERSIONS=["v1", "v2"], APIVER_ROOT_DIR=None)
def test_versions_configured_without_a_root_dir_raises_a_manifest_error():
    with pytest.raises(ManifestError):
        build_manifest()


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["does_not_exist"])
def test_a_version_name_that_fails_to_import_raises_a_manifest_error():
    with pytest.raises(ManifestError):
        build_manifest()


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["notaversion"])
def test_a_version_name_pointing_at_a_non_version_raises_a_manifest_error():
    with pytest.raises(ManifestError):
        build_manifest()


def test_manifest_path_defaults_to_apiver_toml_in_the_current_directory():
    # tests/settings.py never sets APIVER_MANIFEST_PATH.
    assert manifest_path().name == "apiver.toml"
    assert manifest_path().parent.samefile(".")


def test_manifest_path_honors_an_explicit_path():
    assert manifest_path("/tmp/somewhere/apiver.toml").name == "apiver.toml"
    assert str(manifest_path("/tmp/somewhere/apiver.toml")) == "/tmp/somewhere/apiver.toml"


def test_load_committed_manifest_returns_none_when_the_file_is_missing(tmp_path):
    assert load_committed_manifest(tmp_path / "does-not-exist.toml") is None


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["v1", "v2"])
def test_check_manifest_freshness_is_a_noop_without_apiver_versions_configured():
    with override_settings(APIVER_VERSIONS=[]):
        assert check_manifest_freshness() == []


def test_check_manifest_freshness_warns_when_the_manifest_is_missing(tmp_path):
    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_VERSIONS=["v1", "v2"],
        APIVER_MANIFEST_PATH=str(tmp_path / "apiver.toml"),
    ):
        messages = check_manifest_freshness()

    assert len(messages) == 1
    assert isinstance(messages[0], Warning)
    assert messages[0].id == "apiver.W001"


def test_check_manifest_freshness_is_silent_once_the_manifest_matches(tmp_path):
    manifest_file = tmp_path / "apiver.toml"
    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_VERSIONS=["v1", "v2"],
        APIVER_MANIFEST_PATH=str(manifest_file),
    ):
        manifest_file.write_text(tomli_w.dumps(build_manifest()))
        assert check_manifest_freshness() == []


def test_check_manifest_freshness_warns_once_the_manifest_drifts(tmp_path):
    manifest_file = tmp_path / "apiver.toml"
    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_VERSIONS=["v1", "v2"],
        APIVER_MANIFEST_PATH=str(manifest_file),
    ):
        stale = build_manifest()
        stale["versions"]["v2"]["deprecated"] = False
        manifest_file.write_text(tomli_w.dumps(stale))
        messages = check_manifest_freshness()

    assert len(messages) == 1
    assert messages[0].id == "apiver.W001"


def test_check_manifest_freshness_reports_a_configuration_error_loudly(tmp_path):
    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_VERSIONS=["does_not_exist"],
        APIVER_MANIFEST_PATH=str(tmp_path / "apiver.toml"),
    ):
        messages = check_manifest_freshness()

    assert len(messages) == 1
    assert isinstance(messages[0], Error)
    assert messages[0].id == "apiver.E004"


def test_the_freshness_check_is_registered_with_djangos_check_framework():
    assert check_manifest_freshness in registry.registered_checks


def test_manifest_diff_reports_a_missing_committed_manifest(tmp_path):
    with override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["v1", "v2"]):
        _, current, committed = manifest_diff(tmp_path / "apiver.toml")

    assert committed is None
    assert current["versions"]["v1"]["frozen"] is True


def test_alias_target_is_referenced_by_object_not_by_a_copy():
    assert stable.target is v2


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=[])
def test_check_max_live_versions_is_a_noop_without_apiver_versions_configured():
    assert check_max_live_versions() == []


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["v1", "v2"])
def test_check_max_live_versions_is_silent_under_the_default_max():
    assert check_max_live_versions() == []


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["v1", "v2"], APIVER_MAX_LIVE_VERSIONS=1)
def test_check_max_live_versions_warns_once_the_count_exceeds_the_configured_max():
    messages = check_max_live_versions()

    assert len(messages) == 1
    assert isinstance(messages[0], Warning)
    assert messages[0].id == "apiver.W002"
    assert "2 Live Versions" in messages[0].msg
    assert "v1" in messages[0].msg
    assert "v2" in messages[0].msg


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["v1", "v2"], APIVER_MAX_LIVE_VERSIONS=2)
def test_check_max_live_versions_is_silent_exactly_at_the_configured_max():
    assert check_max_live_versions() == []


@override_settings(APIVER_ROOT_DIR=ROOT_DIR, APIVER_VERSIONS=["does_not_exist"])
def test_check_max_live_versions_reports_a_configuration_error_loudly():
    messages = check_max_live_versions()

    assert len(messages) == 1
    assert isinstance(messages[0], Error)
    assert messages[0].id == "apiver.E005"


def test_max_live_versions_check_is_registered_with_djangos_check_framework():
    assert check_max_live_versions in registry.registered_checks
