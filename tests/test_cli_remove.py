"""CLI seam (subprocess) for `apiver remove` (ticket #84). Invokes the entry
point exactly as a user would, against the small independent chains in
tests/fixtures_remove/api/, and restores whatever it wrote afterward.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "tests" / "fixtures_remove" / "api"
AGGREGATION_ROOT = API_DIR / "urls.py"
V2_REGISTRY = API_DIR / "v2" / "registry.py"
V11_REGISTRY = API_DIR / "v11" / "registry.py"
V12_REGISTRY = API_DIR / "v12" / "registry.py"
V21_REGISTRY = API_DIR / "v21" / "registry.py"
V31_REGISTRY = API_DIR / "v31" / "registry.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "tests.fixtures_remove.settings"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def _restore_generated_files():
    paths = [AGGREGATION_ROOT, V2_REGISTRY, V11_REGISTRY, V12_REGISTRY, V21_REGISTRY, V31_REGISTRY]
    originals = {path: path.read_text() for path in paths}
    yield
    for path, original in originals.items():
        path.write_text(original)


def test_remove_writes_the_childs_registry_and_the_aggregation_root():
    result = _run("remove", "v1")

    assert result.returncode == 0, result.stderr
    assert f"wrote {V2_REGISTRY}" in result.stdout
    assert f"wrote {AGGREGATION_ROOT}" in result.stdout

    source = V2_REGISTRY.read_text()
    assert "v2 = Version('v2')" in source
    assert ".derive(" not in source

    aggregation_source = AGGREGATION_ROOT.read_text()
    assert "v1.registry" not in aggregation_source
    assert "include(v1.urls)" not in aggregation_source


def test_remove_reports_the_reparented_children():
    result = _run("remove", "v1")

    assert result.returncode == 0, result.stderr
    assert "v2" in result.stdout
    assert "independent Base Version" in result.stdout


def test_remove_reports_the_settings_cleanup_hint_including_base_version():
    result = _run("remove", "v1")

    assert result.returncode == 0, result.stderr
    assert "APIVER_VERSIONS" in result.stdout
    assert "APIVER_BASE_VERSION" in result.stdout
    assert "git rm -r" in result.stdout


def test_remove_reports_the_settings_cleanup_hint_without_base_version():
    result = _run("remove", "v30", "--force")

    assert result.returncode == 0, result.stderr
    assert "APIVER_VERSIONS" in result.stdout
    assert "APIVER_BASE_VERSION" not in result.stdout


def test_removed_registry_reimports_cleanly_as_a_fresh_base_version():
    """The whole point: the rewritten registry.py must actually work — check
    in a fresh process (not this one, which may have already imported the
    old module) that v2 is now a real, parentless Version resolving exactly
    the routes it did before removal."""
    result = _run("remove", "v1")
    assert result.returncode == 0, result.stderr

    check = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; import os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.fixtures_remove.settings'); "
            "django.setup(); "
            "from tests.fixtures_remove.api.v2.registry import v2; "
            "print(sorted(r.registration.key for r in v2.resolution_table.values())); "
            "print(v2.parent)",
        ],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])},
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr
    routes_line, parent_line = check.stdout.splitlines()
    assert "'payments'" in routes_line
    assert "'ping'" in routes_line
    assert "'schema/'" in routes_line
    assert "'docs/'" in routes_line
    assert parent_line.strip() == "None"


def test_remove_refuses_and_writes_nothing_when_a_child_was_never_squashed():
    before = V21_REGISTRY.read_text()
    aggregation_before = AGGREGATION_ROOT.read_text()

    result = _run("remove", "v20")

    assert result.returncode != 0
    assert "v21" in result.stderr
    assert "apiver squash v21" in result.stderr
    assert V21_REGISTRY.read_text() == before
    assert AGGREGATION_ROOT.read_text() == aggregation_before


def test_remove_refuses_a_version_that_was_never_deprecated():
    result = _run("remove", "v30")

    assert result.returncode != 0
    assert "never deprecated" in result.stderr


def test_remove_force_archives_a_never_deprecated_version():
    result = _run("remove", "v30", "--force")

    assert result.returncode == 0, result.stderr
    source = V31_REGISTRY.read_text()
    assert "v31 = Version('v31')" in source


def test_remove_handles_a_leaf_with_no_children():
    result = _run("remove", "v40")

    assert result.returncode == 0, result.stderr
    assert f"wrote {AGGREGATION_ROOT}" in result.stdout
    aggregation_source = AGGREGATION_ROOT.read_text()
    assert "v40" not in aggregation_source


def test_remove_requires_a_version_argument():
    result = _run("remove")

    assert result.returncode != 0
    assert "version" in result.stderr.lower()
