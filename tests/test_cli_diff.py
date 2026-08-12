"""CLI seam (subprocess) for `apiver diff` (ticket #76). Invokes the entry
point exactly as a user would, against the static fixture graph in
tests/fixtures_diff/api/."""

import json
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


def test_diff_reports_the_removed_list_route():
    result = _run("diff", "v1", "v2")

    assert result.returncode == 0, result.stderr
    assert "GET payments/" in result.stdout
    assert "-" in result.stdout


def test_diff_reports_the_added_field():
    result = _run("diff", "v1", "v2")

    assert result.returncode == 0, result.stderr
    assert "'version'" in result.stdout
    assert "added" in result.stdout


def test_diff_always_prints_the_blind_spots_disclaimer():
    result = _run("diff", "v1", "v2")

    assert "SerializerMethodField" in result.stdout


def test_diff_json_emits_structured_data_and_disclaimer_on_stderr():
    result = _run("diff", "v1", "v2", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert any(f["field"] == "version" for f in payload["fields"])
    assert any(r["path"] == "payments/" and r["kind"] == "removed" for r in payload["resources"])
    assert "SerializerMethodField" in result.stderr


def test_diff_unknown_version_exits_non_zero():
    result = _run("diff", "v1", "v404")

    assert result.returncode != 0
    assert "apiver:" in result.stderr


def test_diff_requires_django_settings_module():
    env = dict(os.environ)
    env.pop("DJANGO_SETTINGS_MODULE", None)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])

    result = subprocess.run(
        [sys.executable, "-m", "apiver.cli", "diff", "v1", "v2"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "DJANGO_SETTINGS_MODULE" in result.stderr
