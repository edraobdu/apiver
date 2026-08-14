"""CLI seam (subprocess) for `apiver init` (ticket 17, ticket 43, ticket #51 —
renamed from `migrate`). Invokes the entry point exactly as a user would,
against the scattered pre-apiver fixture project in tests/fixtures_init/.

`api/v1/` and `api/urls.py` are generated *into the checked-in fixture tree
itself* (the same way a real `manage.py migrate` run would write into a real
project) rather than a copied tmp_path tree, so every test that writes them
cleans up again — see `_clean_generated_root`.
"""

import importlib
import os
import re
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

    result = _run("--base", "v1", "--prefix", "api/", "--manifest-path", str(manifest_target))

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


def test_init_accepts_multiple_prefix_values_and_unions_scattered_routes(tmp_path):
    """ticket #61: a real pre-existing project's routes are rarely all
    under one ancestor. Passing --prefix more than once unions the walk
    across every one of them, keying each discovered route relative to
    whichever prefix it fell under."""
    manifest_target = tmp_path / "apiver.toml"

    result = _run(
        "--base", "v1", "--prefix", "api/", "--prefix", "legacy/", "--manifest-path", str(manifest_target)
    )

    assert result.returncode == 0, result.stderr
    source = (GENERATED_ROOT / "registry.py").read_text()

    # Still picks up everything under "api/", exactly as the single-prefix case.
    assert "v1.register('widgets', WidgetViewSet, basename='widgets')" in source
    assert "v1.register('healthz/', HealthzView, name='healthz')" in source
    # And the scattered route under the second, unrelated ancestor "legacy/",
    # keyed relative to *that* prefix rather than "api/".
    assert "v1.register('archive/', HealthzView, name='legacy-archive')" in source
    # "status/" sits outside both --prefix values and must still be excluded.
    assert "name='status'" not in source

    manifest = tomllib.loads(manifest_target.read_text())
    routes = manifest["versions"]["v1"]["routes"]
    assert len(routes) == 13  # the single-prefix 12 (see above) + legacy/archive/


def test_init_rejects_overlapping_prefix_values(tmp_path):
    """ticket #61's open question, settled: overlapping --prefix values are
    ambiguous (it's unclear which one a route between them belongs to), so
    init refuses outright and writes nothing, rather than silently
    deduping."""
    result = _run(
        "--base",
        "v1",
        "--prefix",
        "api/",
        "--prefix",
        "api/v1/",
        "--manifest-path",
        str(tmp_path / "apiver.toml"),
    )

    assert result.returncode != 0
    assert "overlap" in result.stderr
    assert not GENERATED_ROOT.exists()
    assert not GENERATED_AGGREGATION_ROOT.exists()


def test_init_rejects_duplicate_prefix_values(tmp_path):
    """Passing the same --prefix twice is a degenerate overlap (equal
    strings satisfy the same startswith check) — refused for the same
    reason as any other overlap."""
    result = _run(
        "--base",
        "v1",
        "--prefix",
        "api/",
        "--prefix",
        "api/",
        "--manifest-path",
        str(tmp_path / "apiver.toml"),
    )

    assert result.returncode != 0
    assert "overlap" in result.stderr
    assert not GENERATED_ROOT.exists()


def test_init_writes_a_route_less_base_version_when_nothing_is_discovered(tmp_path):
    """A greenfield project — or one adopted with a --prefix that matches
    nothing at all — is not a failure (ticket #51): `init` still produces a
    valid Base Version, wired with nothing but its own schema/docs routes,
    the same unconditional guarantee `mount` already gives every later
    version."""
    manifest_target = tmp_path / "apiver.toml"

    result = _run("--base", "v1", "--prefix", "nomatch/", "--manifest-path", str(manifest_target))

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
        result = _run("--base", "v1", "--prefix", "api/", "--manifest-path", str(manifest_target))
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
    result = _run("--base", "v1", "--manifest-path", str(tmp_path / "apiver.toml"))

    assert result.returncode == 0, result.stderr
    registry_path = GENERATED_ROOT / "registry.py"
    assert registry_path.is_file()
    # tests/fixtures_init/settings.py's APIVER_ROOT_PREFIX = "api/", the
    # same value the explicit-prefix test passes — same fixture, so the
    # discovered surface is identical.
    assert "v1.register('widgets', WidgetViewSet, basename='widgets')" in registry_path.read_text()


def test_init_refuses_to_overwrite_an_existing_registry(tmp_path):
    first = _run("--base", "v1", "--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))
    assert first.returncode == 0, first.stderr
    written = (GENERATED_ROOT / "registry.py").read_text()

    second = _run("--base", "v1", "--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))

    assert second.returncode != 0
    assert "already exists" in second.stderr
    assert (GENERATED_ROOT / "registry.py").read_text() == written


def test_init_refuses_when_the_aggregation_root_already_mounts_the_base_version(tmp_path):
    first = _run("--base", "v1", "--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))
    assert first.returncode == 0, first.stderr
    # Simulate a re-run after only registry.py was removed by hand — the
    # aggregation root survives untouched, same as a real project's.
    shutil.rmtree(GENERATED_ROOT)

    second = _run("--base", "v1", "--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))

    assert second.returncode != 0
    assert "already mounted" in second.stderr


def test_init_reports_every_diagnostic_and_writes_nothing(tmp_path):
    result = _run(
        "--base",
        "v1",
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


def test_init_requires_base_flag(tmp_path):
    """`--base` (ticket #86) is required, argparse-style, exactly as
    `apiver mount`'s `--from` already is — there's no settings fallback."""
    result = _run("--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))

    assert result.returncode != 0
    assert "--base" in result.stderr
    assert not GENERATED_ROOT.exists()


def test_init_defaults_the_root_dir_when_apiver_root_dir_is_unset(tmp_path):
    """APIVER_ROOT_DIR unset now falls back to "apiversions" (ADR 0003's
    ticket #77 amendment) instead of refusing — run with cwd=tmp_path so the
    freshly-created "apiversions/" package lands there, never in the real
    repo (init would otherwise create it relative to its cwd, ADR 0003
    ticket #77's `_ensure_root_dir_exists` warning notwithstanding)."""
    (tmp_path / "settings_no_root_dir.py").write_text(
        "from tests.fixtures_init.settings import *  # noqa: F403\nAPIVER_ROOT_DIR = None\n"
    )
    env = dict(os.environ)
    env["DJANGO_SETTINGS_MODULE"] = "settings_no_root_dir"
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT), str(tmp_path)])

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apiver.cli",
            "init",
            "--base",
            "v1",
            "--prefix",
            "api/",
            "--manifest-path",
            str(tmp_path / "apiver.toml"),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "apiversions" / "v1" / "registry.py").is_file()
    assert not GENERATED_ROOT.exists()


def test_init_refuses_a_scheme_nonconforming_base_version(tmp_path):
    """ticket #67, ADR 0008 item 5: under the default `sequential` scheme,
    'va' is a valid Python identifier but not a valid slug (its base isn't
    all digits) — init must refuse it before writing anything."""
    result = _run("--base", "va", "--prefix", "api/", "--manifest-path", str(tmp_path / "apiver.toml"))

    assert result.returncode != 0
    assert "does not conform" in result.stderr
    assert "APIVER_VERSION_SCHEME='sequential'" in result.stderr
    assert not (FIXTURE_ROOT / "api" / "va").exists()
    assert not GENERATED_AGGREGATION_ROOT.exists()


def test_init_uses_display_name_in_generated_urls_under_semver_scheme(tmp_path):
    """ADR 0008 item 7: the Aggregation Root's include() line and
    schema_view(prefix=...) use the Scheme's Display Name ('v1.0.0'), while
    the module dotted path and the module-level variable name keep the raw
    slug ('v1_0_0')."""
    generated_root = FIXTURE_ROOT / "api" / "v1_0_0"
    try:
        result = _run(
            "--base",
            "v1_0_0",
            "--prefix",
            "api/",
            "--manifest-path",
            str(tmp_path / "apiver.toml"),
            settings="tests.fixtures_init.settings_semver",
        )

        assert result.returncode == 0, result.stderr
        source = (generated_root / "registry.py").read_text()
        assert "v1_0_0 = Version('v1_0_0')" in source
        assert "v1_0_0.schema_view(prefix='api/v1.0.0/')" in source

        aggregation_source = GENERATED_AGGREGATION_ROOT.read_text()
        assert "from tests.fixtures_init.api.v1_0_0.registry import v1_0_0" in aggregation_source
        assert "    path('api/v1.0.0/', include(v1_0_0.urls))," in aggregation_source
    finally:
        shutil.rmtree(generated_root, ignore_errors=True)
        GENERATED_AGGREGATION_ROOT.unlink(missing_ok=True)


def test_init_uses_display_name_in_generated_urls_under_date_scheme(tmp_path):
    generated_root = FIXTURE_ROOT / "api" / "d2026_08_11"
    try:
        result = _run(
            "--base",
            "d2026_08_11",
            "--prefix",
            "api/",
            "--manifest-path",
            str(tmp_path / "apiver.toml"),
            settings="tests.fixtures_init.settings_date",
        )

        assert result.returncode == 0, result.stderr
        source = (generated_root / "registry.py").read_text()
        assert "d2026_08_11 = Version('d2026_08_11')" in source
        assert "d2026_08_11.schema_view(prefix='api/2026-08-11/')" in source

        aggregation_source = GENERATED_AGGREGATION_ROOT.read_text()
        assert "    path('api/2026-08-11/', include(d2026_08_11.urls))," in aggregation_source
    finally:
        shutil.rmtree(generated_root, ignore_errors=True)
        GENERATED_AGGREGATION_ROOT.unlink(missing_ok=True)


def test_unknown_init_invocation_is_rejected():
    result = _run("--not-a-real-flag")
    assert result.returncode != 0


def test_init_adopts_a_nested_resource_with_a_correct_lookup_regex(tmp_path):
    """Regression test: a nested resource whose parent lookup group is
    embedded in the router's own prefix (no router library, no ancestor
    include() carrying the parameterized segment — tests.fixtures_init.
    urls_nested) must be discovered and adopted with DRF's lookup regex
    intact.

    `_strip_anchors` used to `.replace("^", "")` globally over the
    concatenated ancestor+declared text, which also strips the `^` inside
    DRF's default `[^/.]+` lookup regex the moment it's embedded in a
    prefix (nesting) rather than only ever appearing in the detail route's
    auto-appended, separately-discarded lookup segment (the ordinary,
    non-nested case, which never exercised this). That silently generated
    `'parents/(?P<parent_pk>[/.]+)/children'` — a regex that can only ever
    match a parent_pk made entirely of slashes and dots, i.e. none — so
    every real request 404s despite `init` reporting success.
    """
    generated_root = FIXTURE_ROOT / "api_nested" / "v1"
    generated_aggregation_root = FIXTURE_ROOT / "api_nested" / "urls.py"
    try:
        result = _run(
            "--base",
            "v1",
            "--prefix",
            "",
            "--manifest-path",
            str(tmp_path / "apiver.toml"),
            settings="tests.fixtures_init.settings_nested",
        )

        assert result.returncode == 0, result.stderr
        source = (generated_root / "registry.py").read_text()

        # The bug: this used to read "parents/(?P<parent_pk>[/.]+)/children".
        assert (
            "v1.register('parents/(?P<parent_pk>[^/.]+)/children', ChildViewSet, "
            "basename='parent-children')" in source
        )
        assert "[/.]+" not in source

        # Prove it's not just cosmetic: the generated registry actually
        # resolves a real nested request end to end.
        importlib.invalidate_caches()
        registry = importlib.import_module("tests.fixtures_init.api_nested.v1.registry")
        table = registry.v1.resolution_table
        matches = [path for path in table if "parent_pk" in path]
        assert matches, "no nested route in the composed resolution table"
        assert all("[/.]+" not in path for path in matches)
        assert any(re.match(pattern, "parents/42/children/") for pattern in matches)
    finally:
        shutil.rmtree(generated_root, ignore_errors=True)
        generated_aggregation_root.unlink(missing_ok=True)
        sys.modules.pop("tests.fixtures_init.api_nested.v1.registry", None)
        sys.modules.pop("tests.fixtures_init.api_nested.v1", None)
