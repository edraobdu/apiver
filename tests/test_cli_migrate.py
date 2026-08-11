"""CLI seam (subprocess) for `apiver migrate` (ticket 17). Invokes the
entry point exactly as a user would, against the scattered pre-apiver
fixture project in tests/fixtures_migrate/.

`api/v1/` is generated *into the checked-in fixture tree itself* (the same
way a real `manage.py migrate` run would write into a real project) rather
than a copied tmp_path tree, so every test that writes it cleans it up
again — see `_clean_generated_root`.
"""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures_migrate"
GENERATED_ROOT = FIXTURE_ROOT / "api" / "v1"


def _run(*args: str, settings: str = "tests.fixtures_migrate.settings") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = settings
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", "migrate", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


def _snapshot(root: Path) -> set[str]:
    return {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if "__pycache__" not in path.parts and path.name != ".pytest_cache"
    }


@pytest.fixture(autouse=True)
def _clean_generated_root():
    shutil.rmtree(GENERATED_ROOT, ignore_errors=True)
    yield
    shutil.rmtree(GENERATED_ROOT, ignore_errors=True)


def test_migrate_writes_registry_py_and_the_manifest(tmp_path):
    manifest_target = tmp_path / "apiver.toml"
    before = _snapshot(FIXTURE_ROOT)

    result = _run("--prefix", "api/", "--manifest-path", str(manifest_target))

    assert result.returncode == 0, result.stderr
    assert (GENERATED_ROOT / "__init__.py").is_file()
    registry_path = GENERATED_ROOT / "registry.py"
    assert registry_path.is_file()

    source = registry_path.read_text()
    assert "from apiver.drf import Version" in source
    assert (
        "from tests.fixtures_migrate.views import "
        "GadgetSummaryView, GadgetViewSet, HealthzView, WebhookViewSet, WidgetViewSet, ping"
    ) in source
    assert "v1 = Version('v1')" in source
    assert "v1.register('widgets', WidgetViewSet, basename='widgets')" in source
    assert "v1.register('gadgets', GadgetViewSet, basename='gadgets')" in source
    assert "v1.register('gadgets/summary/', GadgetSummaryView, name='gadgets-summary')" in source
    assert "v1.register('healthz/', HealthzView, name='healthz')" in source
    assert "v1.register('ping/', ping, name='ping')" in source
    assert "v1.register('integrations/webhooks', WebhookViewSet, basename='webhooks')" in source
    # The status/ route sits outside --prefix "api/" and must not appear.
    assert "status" not in source

    assert manifest_target.is_file()
    manifest = tomllib.loads(manifest_target.read_text())
    assert manifest["versions"]["v1"]["frozen"] is False
    assert "parent" not in manifest["versions"]["v1"]
    routes = manifest["versions"]["v1"]["routes"]
    assert len(routes) == 10  # widgets(2) + gadgets(3) + webhooks(2) + 3 single-route views
    assert all(route["source_version"] == "v1" for route in routes.values())

    # Nothing else on disk changed.
    after = _snapshot(FIXTURE_ROOT)
    assert after - before == {"api/v1", "api/v1/__init__.py", "api/v1/registry.py"}
    assert before - after == set()


def test_migrate_refuses_to_overwrite_an_existing_registry(tmp_path):
    first = _run("--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))
    assert first.returncode == 0, first.stderr
    written = (GENERATED_ROOT / "registry.py").read_text()

    second = _run("--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))

    assert second.returncode != 0
    assert "already exists" in second.stderr
    assert (GENERATED_ROOT / "registry.py").read_text() == written


def test_migrate_reports_every_diagnostic_and_writes_nothing(tmp_path):
    result = _run(
        "--prefix",
        "api/",
        "--manifest-path",
        str(tmp_path / "apiver.toml"),
        settings="tests.fixtures_migrate.bad_settings",
    )

    assert result.returncode != 0
    assert "F1" in result.stderr or "closure" in result.stderr
    assert "lambda" in result.stderr
    assert not GENERATED_ROOT.exists()


def test_migrate_requires_apiver_base_version(tmp_path):
    (tmp_path / "settings_no_base.py").write_text(
        "from tests.fixtures_migrate.settings import *  # noqa: F403\nAPIVER_BASE_VERSION = None\n"
    )
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "settings_no_base"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT), str(tmp_path)])

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apiver.cli",
            "migrate",
            "--prefix",
            "api/",
            "--manifest-path",
            str(tmp_path / "apiver.toml"),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "APIVER_BASE_VERSION" in result.stderr
    assert not GENERATED_ROOT.exists()


def test_unknown_migrate_invocation_requires_prefix():
    result = _run()
    assert result.returncode != 0
