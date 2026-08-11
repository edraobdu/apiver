"""CLI seam (subprocess) for `apiver init` (ticket 17, ticket 43, ticket #51 —
renamed from `migrate`). Invokes the entry point exactly as a user would,
against the scattered pre-apiver fixture project in tests/fixtures_init/.

`api/v1/` and `api/urls.py` are generated *into the checked-in fixture tree
itself* (the same way a real `manage.py migrate` run would write into a real
project) rather than a copied tmp_path tree, so every test that writes them
cleans up again — see `_clean_generated_root`.
"""

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures_init"
GENERATED_ROOT = FIXTURE_ROOT / "api" / "v1"
GENERATED_AGGREGATION_ROOT = FIXTURE_ROOT / "api" / "urls.py"


def _run(*args: str, settings: str = "tests.fixtures_init.settings") -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = settings
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", "init", *args],
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
    GENERATED_AGGREGATION_ROOT.unlink(missing_ok=True)
    yield
    shutil.rmtree(GENERATED_ROOT, ignore_errors=True)
    GENERATED_AGGREGATION_ROOT.unlink(missing_ok=True)


def test_init_writes_registry_py_the_aggregation_root_and_the_manifest(tmp_path):
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
        "from tests.fixtures_init.views import "
        "GadgetSummaryView, GadgetViewSet, HealthzView, WebhookViewSet, WidgetViewSet, ping"
    ) in source
    assert "v1 = Version('v1')" in source
    assert "v1.register('widgets', WidgetViewSet, basename='widgets')" in source
    assert "v1.register('gadgets', GadgetViewSet, basename='gadgets')" in source
    assert "v1.register('gadgets/summary/', GadgetSummaryView, name='gadgets-summary')" in source
    assert "v1.register('healthz/', HealthzView, name='healthz')" in source
    assert "v1.register('ping/', ping, name='ping')" in source
    assert "v1.register('integrations/webhooks', WebhookViewSet, basename='webhooks')" in source
    # ticket #40: the unscoped SpectacularAPIView is not registered raw —
    # it's rewired through schema_view(prefix=...), scoped to this
    # version's own absolute mount, so a sibling version can never leak in.
    assert "v1.register('schema/', v1.schema_view(prefix='api/v1/'), name='v1-schema')" in source
    assert "SpectacularAPIView" not in source
    # ticket 22: SpectacularSwaggerView is rewired too, through v1.docs_view()
    # (mirroring v1.schema_view() above) rather than a bare .as_view() call —
    # its own registration name is qualified ("v1-docs", not the bare,
    # pre-existing "docs") and docs_view() points it at v1's own qualified
    # schema name internally, so it can't collide with (or silently resolve
    # to) a same-named route kept mounted elsewhere in the project. No import
    # needed either: the discovered class is the exact, unmodified default
    # docs_view() already falls back to.
    assert "v1.register('docs/', v1.docs_view(), name='v1-docs')" in source
    assert "SpectacularSwaggerView" not in source
    # The schema registration is emitted last: schema_view() snapshots
    # self.urls the moment it's called, so every other route must already
    # be registered for the generated schema to describe the whole surface.
    other_keys = (
        "widgets",
        "gadgets",
        "gadgets/summary/",
        "healthz/",
        "ping/",
        "integrations/webhooks",
        "docs/",
    )
    assert source.rindex("v1.register('schema/'") > max(
        source.rindex(f"v1.register({key!r}") for key in other_keys
    )
    # The status/ route sits outside --prefix "api/" and must not appear.
    assert "status" not in source

    aggregation_path = GENERATED_AGGREGATION_ROOT
    assert aggregation_path.is_file()
    aggregation_source = aggregation_path.read_text()
    assert "from django.urls import include, path" in aggregation_source
    assert "from tests.fixtures_init.api.v1.registry import v1" in aggregation_source
    assert "    path('api/v1/', include(v1.urls))," in aggregation_source

    assert manifest_target.is_file()
    manifest = tomllib.loads(manifest_target.read_text())
    assert manifest["versions"]["v1"]["frozen"] is False
    assert "parent" not in manifest["versions"]["v1"]
    routes = manifest["versions"]["v1"]["routes"]
    assert len(routes) == 12  # widgets(2) + gadgets(3) + webhooks(2) + 3 single-route views + schema + docs
    assert all(route["source_version"] == "v1" for route in routes.values())

    # Nothing else on disk changed.
    after = _snapshot(FIXTURE_ROOT)
    assert after - before == {"api/v1", "api/v1/__init__.py", "api/v1/registry.py", "api/urls.py"}
    assert before - after == set()


def test_init_writes_a_route_less_base_version_when_nothing_is_discovered(tmp_path):
    """A greenfield project — or one adopted with a --prefix that matches
    nothing at all — is not a failure (ticket #51): `init` still produces a
    valid Base Version, wired with nothing but its own schema/docs routes,
    the same unconditional guarantee `mount` already gives every later
    version."""
    manifest_target = tmp_path / "apiver.toml"

    result = _run("--prefix", "nomatch/", "--manifest-path", str(manifest_target))

    assert result.returncode == 0, result.stderr
    registry_path = GENERATED_ROOT / "registry.py"
    source = registry_path.read_text()

    assert "v1 = Version('v1')" in source
    assert "v1.register('schema/', v1.schema_view(prefix='api/v1/'), name='v1-schema')" in source
    assert "v1.register('docs/', v1.docs_view(), name='v1-docs')" in source
    # Nothing under --prefix "nomatch/" was discovered — no other register()
    # calls at all.
    assert source.count("v1.register(") == 2

    assert manifest_target.is_file()
    manifest = tomllib.loads(manifest_target.read_text())
    routes = manifest["versions"]["v1"]["routes"]
    assert len(routes) == 2  # schema + docs only


def test_init_creates_the_root_package_when_it_does_not_exist_yet(tmp_path):
    """The very first `init` run in a project that has never used apiver
    before has no `APIVER_ROOT_DIR` package on disk at all — not even an empty
    one. Nothing else, before this, ever had a reason to create it, so `init`
    must (a developer should never be told to `mkdir`/`touch __init__.py`
    themselves before running the one command that adopts their project)."""
    manifest_target = tmp_path / "apiver.toml"
    api_dir = FIXTURE_ROOT / "api"
    shutil.rmtree(api_dir)
    before = _snapshot(FIXTURE_ROOT)

    try:
        result = _run("--prefix", "api/", "--manifest-path", str(manifest_target))
    finally:
        # Restore the checked-in (empty) api/__init__.py the rest of this
        # module's tests assume is already there, regardless of outcome.
        api_dir.mkdir(exist_ok=True)
        (api_dir / "__init__.py").touch(exist_ok=True)

    assert result.returncode == 0, result.stderr
    assert (GENERATED_ROOT / "registry.py").is_file()

    after = _snapshot(FIXTURE_ROOT)
    assert after - before == {
        "api",
        "api/__init__.py",
        "api/v1",
        "api/v1/__init__.py",
        "api/v1/registry.py",
        "api/urls.py",
    }


def test_init_infers_prefix_from_root_prefix_setting_when_unset(tmp_path):
    result = _run("--manifest-path", str(tmp_path / "apiver.toml"))

    assert result.returncode == 0, result.stderr
    registry_path = GENERATED_ROOT / "registry.py"
    assert registry_path.is_file()
    # tests/fixtures_init/settings.py's APIVER_ROOT_PREFIX = "api/", the
    # same value the explicit-prefix test passes — same fixture, so the
    # discovered surface is identical.
    assert "v1.register('widgets', WidgetViewSet, basename='widgets')" in registry_path.read_text()


def test_init_refuses_to_overwrite_an_existing_registry(tmp_path):
    first = _run("--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))
    assert first.returncode == 0, first.stderr
    written = (GENERATED_ROOT / "registry.py").read_text()

    second = _run("--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))

    assert second.returncode != 0
    assert "already exists" in second.stderr
    assert (GENERATED_ROOT / "registry.py").read_text() == written


def test_init_refuses_when_the_aggregation_root_already_mounts_the_base_version(tmp_path):
    first = _run("--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))
    assert first.returncode == 0, first.stderr
    # Simulate a re-run after only registry.py was removed by hand — the
    # aggregation root survives untouched, same as a real project's.
    shutil.rmtree(GENERATED_ROOT)

    second = _run("--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))

    assert second.returncode != 0
    assert "already mounted" in second.stderr


def test_init_reports_every_diagnostic_and_writes_nothing(tmp_path):
    result = _run(
        "--prefix",
        "api/",
        "--manifest-path",
        str(tmp_path / "apiver.toml"),
        settings="tests.fixtures_init.bad_settings",
    )

    assert result.returncode != 0
    assert "F1" in result.stderr or "closure" in result.stderr
    assert "lambda" in result.stderr
    assert not GENERATED_ROOT.exists()
    assert not GENERATED_AGGREGATION_ROOT.exists()


def test_init_requires_apiver_base_version(tmp_path):
    (tmp_path / "settings_no_base.py").write_text(
        "from tests.fixtures_init.settings import *  # noqa: F403\nAPIVER_BASE_VERSION = None\n"
    )
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "settings_no_base"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT), str(tmp_path)])

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apiver.cli",
            "init",
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


def test_init_requires_apiver_root_dir(tmp_path):
    (tmp_path / "settings_no_root_dir.py").write_text(
        "from tests.fixtures_init.settings import *  # noqa: F403\nAPIVER_ROOT_DIR = None\n"
    )
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "settings_no_root_dir"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT), str(tmp_path)])

    result = subprocess.run(
        [sys.executable, "-m", "apiver.cli", "init", "--manifest-path", str(tmp_path / "apiver.toml")],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "APIVER_ROOT_DIR" in result.stderr
    assert not GENERATED_ROOT.exists()


def test_unknown_init_invocation_is_rejected():
    result = _run("--not-a-real-flag")
    assert result.returncode != 0
