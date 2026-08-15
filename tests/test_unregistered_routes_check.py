"""`check_unregistered_urlconf_routes` (`apiver.E012`, ticket #106): flags a
route hand-added to `ROOT_URLCONF` outside every configured Live Version's
own mount, without also flagging the pre-adoption dual-mounted surface ADR
0007's adoption story deliberately leaves in place.
"""

import tomli_w
from django.core.checks import Error
from django.core.checks.registry import registry
from django.test import override_settings

from apiver.drf import check_unregistered_urlconf_routes
from apiver.drf.manifest import build_manifest

ROOT_DIR = "tests.fixtures_urlconf_check.api"
BASELINE_URLCONF = "tests.fixtures_urlconf_check.urls_baseline"
AFTER_URLCONF = "tests.fixtures_urlconf_check.urls_after"


def _write_baseline_manifest(manifest_path):
    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_ROOT_PREFIX="api/",
        APIVER_VERSIONS=["v1"],
        ROOT_URLCONF=BASELINE_URLCONF,
    ):
        manifest_path.write_text(tomli_w.dumps(build_manifest()))


def test_the_check_is_registered_with_djangos_check_framework():
    assert check_unregistered_urlconf_routes in registry.registered_checks


def test_is_a_noop_without_apiver_versions_configured():
    with override_settings(APIVER_VERSIONS=[]):
        assert check_unregistered_urlconf_routes() == []


def test_is_a_noop_when_no_manifest_has_ever_been_written(tmp_path):
    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_ROOT_PREFIX="api/",
        APIVER_VERSIONS=["v1"],
        ROOT_URLCONF=BASELINE_URLCONF,
        APIVER_MANIFEST_PATH=str(tmp_path / "apiver.toml"),
    ):
        assert check_unregistered_urlconf_routes() == []


def test_the_pre_adoption_dual_mounted_surface_is_not_falsely_flagged(tmp_path):
    """Case (b): `legacy/` was already there the last time `apiver manifest`
    ran, and the URLconf hasn't changed since — it must stay silent."""
    manifest_path = tmp_path / "apiver.toml"
    _write_baseline_manifest(manifest_path)

    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_ROOT_PREFIX="api/",
        APIVER_VERSIONS=["v1"],
        ROOT_URLCONF=BASELINE_URLCONF,
        APIVER_MANIFEST_PATH=str(manifest_path),
    ):
        assert check_unregistered_urlconf_routes() == []


def test_a_route_hand_added_the_old_way_after_adoption_is_flagged(tmp_path):
    """Case (a): `legacy/new-route/` wasn't present at the last `apiver
    manifest` run — it must be flagged, without also re-flagging `legacy/`
    itself."""
    manifest_path = tmp_path / "apiver.toml"
    _write_baseline_manifest(manifest_path)

    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_ROOT_PREFIX="api/",
        APIVER_VERSIONS=["v1"],
        ROOT_URLCONF=AFTER_URLCONF,
        APIVER_MANIFEST_PATH=str(manifest_path),
    ):
        messages = check_unregistered_urlconf_routes()

    assert len(messages) == 1
    assert isinstance(messages[0], Error)
    assert messages[0].id == "apiver.E012"
    assert "legacy/new-route/" in messages[0].msg
    assert "'legacy/'" not in messages[0].msg


def test_running_apiver_manifest_again_absorbs_the_new_route_into_the_baseline(tmp_path):
    """The known staleness-idiom tradeoff (ticket #106): regenerating the
    manifest against the drifted URLconf re-baselines it, so the check goes
    quiet again — `check_manifest_freshness` (apiver.W001) is what nags a
    developer to look at *why* the manifest changed before doing that."""
    manifest_path = tmp_path / "apiver.toml"
    _write_baseline_manifest(manifest_path)

    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_ROOT_PREFIX="api/",
        APIVER_VERSIONS=["v1"],
        ROOT_URLCONF=AFTER_URLCONF,
        APIVER_MANIFEST_PATH=str(manifest_path),
    ):
        manifest_path.write_text(tomli_w.dumps(build_manifest()))
        assert check_unregistered_urlconf_routes() == []
