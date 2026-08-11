"""CLI seam (subprocess) for `apiver mount` (ticket 43, ADR 0007 item 7).
Invokes the entry point exactly as a user would, against
tests/fixtures_mount/ — a project with v1/v2 registries already authored by
hand but no aggregation root yet, so every test writes/extends
`api/urls.py` itself and cleans it up again.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures_mount"
AGGREGATION_ROOT = FIXTURE_ROOT / "api" / "urls.py"
V2_REGISTRY = FIXTURE_ROOT / "api" / "v2" / "registry.py"
V3_REGISTRY = FIXTURE_ROOT / "api" / "v3" / "registry.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "tests.fixtures_mount.settings"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", "mount", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def _clean_aggregation_root():
    AGGREGATION_ROOT.unlink(missing_ok=True)
    yield
    AGGREGATION_ROOT.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _restore_v2_registry():
    # Mounting v2 now writes its own schema override into registry.py
    # (ticket #47), unlike every other mount test's `api/urls.py`-only
    # side effect — autouse, so every test starts from the hand-authored
    # fixture, not whatever an earlier test's mount left behind.
    original = V2_REGISTRY.read_text()
    yield
    V2_REGISTRY.write_text(original)


def test_mount_seeds_the_aggregation_root_as_the_first_mount():
    result = _run("v1")

    assert result.returncode == 0, result.stderr
    assert AGGREGATION_ROOT.is_file()
    source = AGGREGATION_ROOT.read_text()
    assert "from django.urls import include, path" in source
    assert "from tests.fixtures_mount.api.v1.registry import v1" in source
    assert "    path('api/v1/', include(v1.urls))," in source


def test_mount_extends_an_existing_aggregation_root():
    first = _run("v1")
    assert first.returncode == 0, first.stderr

    second = _run("v2")

    assert second.returncode == 0, second.stderr
    source = AGGREGATION_ROOT.read_text()
    assert "from tests.fixtures_mount.api.v1.registry import v1" in source
    assert "from tests.fixtures_mount.api.v2.registry import v2" in source
    assert "    path('api/v1/', include(v1.urls))," in source
    assert "    path('api/v2/', include(v2.urls))," in source


def test_mount_refuses_to_mount_the_same_version_twice():
    first = _run("v1")
    assert first.returncode == 0, first.stderr
    written = AGGREGATION_ROOT.read_text()

    second = _run("v1")

    assert second.returncode != 0
    assert "already mounted" in second.stderr
    assert AGGREGATION_ROOT.read_text() == written


def test_mount_refuses_a_version_with_no_registry_py():
    result = _run("vnothing")

    assert result.returncode != 0
    assert "could not be imported" in result.stderr
    assert not AGGREGATION_ROOT.exists()


def test_mount_refuses_a_dotted_path_that_is_not_a_version_instance():
    result = _run("notaversion")

    assert result.returncode != 0
    assert "is not a Version instance" in result.stderr
    assert not AGGREGATION_ROOT.exists()


def test_mount_requires_apiver_root_dir(tmp_path):
    (tmp_path / "settings_no_root_dir.py").write_text(
        "from tests.fixtures_mount.settings import *  # noqa: F403\nAPIVER_ROOT_DIR = None\n"
    )
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "settings_no_root_dir"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT), str(tmp_path)])

    result = subprocess.run(
        [sys.executable, "-m", "apiver.cli", "mount", "v1"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "APIVER_ROOT_DIR" in result.stderr
    assert not AGGREGATION_ROOT.exists()


def test_mount_wires_an_authored_versions_own_schema_override():
    """v2 derives from v1, which already has a 'schema' Registration
    (ticket #47) — mount should append v2's own override, reusing v1's
    'schema/' key but always naming it 'schema' (Version.schema_route_name
    for a version with a parent)."""
    result = _run("v2")

    assert result.returncode == 0, result.stderr
    assert f"wrote {V2_REGISTRY}" in result.stdout
    source = V2_REGISTRY.read_text()
    assert "v2.override('schema/', v2.schema_view(prefix='api/v2/'), name='schema')" in source


def test_mount_does_not_duplicate_an_already_present_schema_override():
    first = _run("v2")
    assert first.returncode == 0, first.stderr
    written = V2_REGISTRY.read_text()

    # Only the aggregation root refuses a second mount of the same version
    # (already-mounted check); removing it lets a second run reach the
    # schema-override step again, against a registry.py that already has
    # its own override from the first run.
    AGGREGATION_ROOT.unlink()

    second = _run("v2")

    assert second.returncode == 0, second.stderr
    assert f"wrote {V2_REGISTRY}" not in second.stdout
    assert V2_REGISTRY.read_text() == written


def test_mount_skips_the_schema_override_when_no_ancestor_has_one():
    """v3 has no parent and no schema Registration of its own — there is
    nothing to inherit a key/name from, so mount silently skips writing a
    schema override (ticket #47's no-ancestor-schema-registration case)."""
    original = V3_REGISTRY.read_text()

    result = _run("v3")

    assert result.returncode == 0, result.stderr
    assert f"wrote {V3_REGISTRY}" not in result.stdout
    assert V3_REGISTRY.read_text() == original


def test_mount_requires_django_settings_module():
    env = dict(os.environ)
    env.pop("DJANGO_SETTINGS_MODULE", None)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])

    result = subprocess.run(
        [sys.executable, "-m", "apiver.cli", "mount", "v1"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DJANGO_SETTINGS_MODULE" in result.stderr
