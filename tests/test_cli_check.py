"""CLI seam (subprocess) for `apiver check` (ticket #76). Every schema
diff is treated as already declared — check reports rather than gates
(user decision recorded in the ticket) — so it exits non-zero only on a
tool/config error, never because a diff found changes."""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "tests.fixtures_diff.settings"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def test_check_with_no_arguments_checks_every_authored_apiver_version():
    result = _run("check")

    assert result.returncode == 0, result.stderr
    assert "v1 -> v2" in result.stdout
    assert "'version'" in result.stdout


def test_check_always_prints_the_blind_spots_disclaimer():
    result = _run("check")

    assert "SerializerMethodField" in result.stdout


def test_check_reports_a_permission_classes_change():
    result = _run("check")

    assert result.returncode == 0, result.stderr
    assert "permission_classes changed on 'payments'" in result.stdout


def test_check_exits_zero_even_though_breaking_changes_are_present():
    result = _run("check")

    assert result.returncode == 0, result.stderr
    assert "breaking change" in result.stdout


def test_check_accepts_explicit_version_arguments():
    result = _run("check", "v2")

    assert result.returncode == 0, result.stderr
    assert "v1 -> v2" in result.stdout


def test_check_skips_the_base_version_with_no_parent():
    result = _run("check", "v1")

    assert result.returncode == 0, result.stderr
    assert "no authored versions" in result.stdout


def test_check_unknown_version_exits_non_zero():
    result = _run("check", "v404")

    assert result.returncode != 0
    assert "apiver:" in result.stderr
