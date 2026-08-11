"""CLI seam (subprocess) for `apiver versions` (ticket 17). Runs against a
manifest generated from the same static fixture graph test_cli_manifest.py
uses (tests/fixtures_manifest/api/), and — unlike `manifest`/
`init` — with no DJANGO_SETTINGS_MODULE set at all, proving the command
works from apiver.toml alone (spec item 66)."""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str, django_settings: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if django_settings:
        env["DJANGO_SETTINGS_MODULE"] = "tests.fixtures_manifest.settings"
    else:
        env.pop("DJANGO_SETTINGS_MODULE", None)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def _write_fixture_manifest(target: Path) -> None:
    write_result = _run("manifest", "--path", str(target))
    assert write_result.returncode == 0, write_result.stderr


def test_versions_prints_lineage_frozen_status_and_lifecycle(tmp_path):
    target = tmp_path / "apiver.toml"
    _write_fixture_manifest(target)

    result = _run("versions", "--path", str(target), django_settings=False)

    assert result.returncode == 0, result.stderr
    assert "v1 (base version) — frozen, live" in result.stdout
    assert "v2 (derived from v1) — mutable, deprecated (sunset 2030-01-01T00:00:00+00:00)" in result.stdout


def test_versions_prints_alias_pointers(tmp_path):
    target = tmp_path / "apiver.toml"
    _write_fixture_manifest(target)

    result = _run("versions", "--path", str(target), django_settings=False)

    assert result.returncode == 0, result.stderr
    assert "aliases: stable" in result.stdout


def test_versions_splits_defined_from_inherited_routes(tmp_path):
    target = tmp_path / "apiver.toml"
    _write_fixture_manifest(target)

    result = _run("versions", "--path", str(target), django_settings=False)

    assert result.returncode == 0, result.stderr
    # v2 overrides "payments" (the detail route) but inherits "ping" from v1.
    assert "routes: 1 defined, 1 inherited" in result.stdout
    assert "inherits from v1:" in result.stdout


def test_versions_exits_non_zero_when_the_manifest_is_missing(tmp_path):
    target = tmp_path / "apiver.toml"

    result = _run("versions", "--path", str(target), django_settings=False)

    assert result.returncode != 0
    assert "does not exist" in result.stderr


def test_versions_does_not_require_django_settings_module():
    env = dict(os.environ)
    env.pop("DJANGO_SETTINGS_MODULE", None)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])

    result = subprocess.run(
        [sys.executable, "-m", "apiver.cli", "versions", "--path", "/nonexistent/apiver.toml"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    # Fails on the missing manifest, not on the missing settings module.
    assert "DJANGO_SETTINGS_MODULE" not in result.stderr
    assert "does not exist" in result.stderr
