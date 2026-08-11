"""CLI seam (subprocess) for `apiver manifest`/`apiver manifest --check`
(ticket 16). Invokes the entry point exactly as a user would, against the
static fixture graph in tests/fixtures_manifest/registry.py."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "tests.fixtures_manifest.settings"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", *args],
        cwd=str(cwd or REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def test_manifest_writes_a_toml_file_mirroring_the_live_versions(tmp_path):
    target = tmp_path / "apiver.toml"

    result = _run("manifest", "--path", str(target))

    assert result.returncode == 0, result.stderr
    assert target.is_file()

    written = tomllib.loads(target.read_text())
    assert written["versions"]["v1"]["frozen"] is True
    assert written["versions"]["v2"]["parent"] == "v1"
    assert written["versions"]["v2"]["deprecated"] is True
    assert written["aliases"] == {"stable": "v2"}


def test_manifest_check_exits_non_zero_when_the_file_is_missing(tmp_path):
    target = tmp_path / "apiver.toml"

    result = _run("manifest", "--check", "--path", str(target))

    assert result.returncode != 0
    assert "does not exist" in result.stderr


def test_manifest_check_exits_zero_right_after_writing(tmp_path):
    target = tmp_path / "apiver.toml"
    write_result = _run("manifest", "--path", str(target))
    assert write_result.returncode == 0, write_result.stderr

    check_result = _run("manifest", "--check", "--path", str(target))

    assert check_result.returncode == 0, check_result.stderr


def test_manifest_check_exits_non_zero_when_the_file_is_stale(tmp_path):
    target = tmp_path / "apiver.toml"
    write_result = _run("manifest", "--path", str(target))
    assert write_result.returncode == 0, write_result.stderr

    target.write_text(target.read_text().replace("deprecated = true", "deprecated = false"))

    check_result = _run("manifest", "--check", "--path", str(target))

    assert check_result.returncode != 0
    assert "stale" in check_result.stderr


def test_manifest_requires_django_settings_module(tmp_path):
    env = dict(os.environ)
    env.pop("DJANGO_SETTINGS_MODULE", None)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])

    result = subprocess.run(
        [sys.executable, "-m", "apiver.cli", "manifest", "--path", str(tmp_path / "apiver.toml")],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DJANGO_SETTINGS_MODULE" in result.stderr


@pytest.mark.parametrize("args", [(), ("--path", "/tmp/apiver.toml")])
def test_unknown_command_is_rejected(args):
    result = _run("not-a-real-command", *args)
    assert result.returncode != 0
