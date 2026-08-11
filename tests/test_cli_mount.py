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
