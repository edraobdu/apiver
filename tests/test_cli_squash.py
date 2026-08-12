"""CLI seam (subprocess) for `apiver squash` (ticket #77, ADR 0009). Invokes
the entry point exactly as a user would, against the real v1 <- v2 <- v3
chain in tests/fixtures_squash/api/ — writes into that checked-in fixture
tree the same way `apiver mount`'s CLI tests already do, and restores it
afterward.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
V3_REGISTRY = REPO_ROOT / "tests" / "fixtures_squash" / "api" / "v3" / "registry.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "tests.fixtures_squash.settings"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def _restore_v3_registry():
    original = V3_REGISTRY.read_text()
    yield
    V3_REGISTRY.write_text(original)


def test_squash_writes_the_flattened_registry():
    result = _run("squash", "v3")

    assert result.returncode == 0, result.stderr
    assert f"wrote {V3_REGISTRY}" in result.stdout
    source = V3_REGISTRY.read_text()
    assert "v3 = v2.derive('v3')" in source
    assert ".register(" not in source  # every absorbed key is override() — v2 still resolves them all


def test_squash_reports_the_absorbed_versions():
    result = _run("squash", "v3")

    assert result.returncode == 0, result.stderr
    assert "v1, v2" in result.stdout
    assert "apiver remove" in result.stdout
    assert "safe to remove yet" in result.stdout


def test_squashed_registry_is_valid_python_that_reimports_cleanly():
    """The whole point: the file squash just wrote must actually work —
    reimport it in a fresh process and check its resolved routes match what
    the pre-squash chain already resolved (payments/refunds/schema/docs,
    ping gone) and that its parent chain is unchanged, not just that squash
    *said* it wrote something. This is the exact check that caught two real
    bugs during review: register() vs override() (ImportError-on-reimport)
    and a dropped remove() call (ping silently resurrected)."""
    result = _run("squash", "v3")
    assert result.returncode == 0, result.stderr

    check = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; import os; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.fixtures_squash.settings'); "
            "django.setup(); "
            "from tests.fixtures_squash.api.v3.registry import v3; "
            "print(sorted(v3.resolution_table.keys())); "
            "print(v3.parent.name if v3.parent else None)",
        ],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])},
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr
    routes_line, parent_line = check.stdout.splitlines()
    assert "payments" in routes_line
    assert "refunds" in routes_line
    assert "ping" not in routes_line
    assert parent_line.strip() == "v2"


def test_squash_refuses_a_version_with_no_parent():
    result = _run("squash", "v1")

    assert result.returncode != 0
    assert "Base Version" in result.stderr


def test_squash_refuses_and_writes_nothing_when_an_absorbed_version_is_dirty():
    dirty_child_registry = REPO_ROOT / "tests" / "fixtures_squash" / "api" / "dirty_child" / "registry.py"
    before = dirty_child_registry.read_text()

    result = _run("squash", "dirty_child")

    assert result.returncode != 0
    assert "dirty_base" in result.stderr
    assert "InlineInDirtyBase" in result.stderr
    assert "stray.py" in result.stderr
    assert dirty_child_registry.read_text() == before


def test_squash_requires_a_version_argument():
    result = _run("squash")

    assert result.returncode != 0
    assert "version" in result.stderr.lower()
