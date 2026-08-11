"""CLI seam (subprocess) for `apiver --settings` and its
`[tool.apiver].django_settings_module` pyproject.toml fallback (ticket #54).
Resolution order is flag -> DJANGO_SETTINGS_MODULE env var -> pyproject.toml
-> the existing "not set" error, mirroring pytest-django's own `--ds`
precedence. `mount` against `tests/fixtures_mount/` is the vehicle — any
Django-settings-requiring subcommand would do, but it's already exercised
elsewhere in the suite, so reaching a real "wrote ..." success line here is
solid proof resolution actually fed `DJANGO_SETTINGS_MODULE` before
`django.setup()`.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures_mount"
API_DIR = FIXTURE_ROOT / "api"
AGGREGATION_ROOT = API_DIR / "urls.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

_FIXTURE_ENTRIES = {"v0", "v1", "notaversion", "__init__.py", "__pycache__"}


def _run(
    *args: str, settings_env: str | None = "tests.fixtures_mount.settings"
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if settings_env is None:
        env.pop("DJANGO_SETTINGS_MODULE", None)
    else:
        env["DJANGO_SETTINGS_MODULE"] = settings_env
    env["PYTHONPATH"] = os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "apiver.cli", *args],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def _clean_generated_output():
    AGGREGATION_ROOT.unlink(missing_ok=True)
    yield
    AGGREGATION_ROOT.unlink(missing_ok=True)
    for child in API_DIR.iterdir():
        if child.name not in _FIXTURE_ENTRIES:
            shutil.rmtree(child)


@pytest.fixture
def pyproject_apiver_section():
    """Temporarily appends a `[tool.apiver]` section to the repo's own
    pyproject.toml — resolution reads it from `./pyproject.toml` relative
    to cwd (no upward search), and these subprocess tests always run with
    cwd=REPO_ROOT (mount's own path-writing logic depends on it)."""
    original = PYPROJECT_PATH.read_text()

    def _write(django_settings_module: str) -> None:
        PYPROJECT_PATH.write_text(
            original + f'\n[tool.apiver]\ndjango_settings_module = "{django_settings_module}"\n'
        )

    yield _write
    PYPROJECT_PATH.write_text(original)


def test_settings_flag_resolves_and_is_used():
    result = _run(
        "--settings",
        "tests.fixtures_mount.settings",
        "mount",
        "v2",
        "--from",
        "v1",
        settings_env=None,
    )

    assert result.returncode == 0, result.stderr
    assert "wrote" in result.stdout


def test_env_var_overrides_a_configured_pyproject_toml_value(pyproject_apiver_section):
    pyproject_apiver_section("not.a.real.settings.module")

    result = _run("mount", "v2", "--from", "v1", settings_env="tests.fixtures_mount.settings")

    assert result.returncode == 0, result.stderr
    assert "wrote" in result.stdout


def test_pyproject_toml_value_used_when_neither_flag_nor_env_set(pyproject_apiver_section):
    pyproject_apiver_section("tests.fixtures_mount.settings")

    result = _run("mount", "v2", "--from", "v1", settings_env=None)

    assert result.returncode == 0, result.stderr
    assert "wrote" in result.stdout


def test_not_set_error_still_fires_when_none_of_the_three_are_present():
    result = _run("mount", "v2", "--from", "v1", settings_env=None)

    assert result.returncode != 0
    assert "DJANGO_SETTINGS_MODULE is not set" in result.stderr
    assert not AGGREGATION_ROOT.exists()


def test_settings_flag_takes_precedence_over_a_configured_pyproject_toml_value(pyproject_apiver_section):
    pyproject_apiver_section("not.a.real.settings.module")

    result = _run(
        "--settings",
        "tests.fixtures_mount.settings",
        "mount",
        "v2",
        "--from",
        "v1",
        settings_env=None,
    )

    assert result.returncode == 0, result.stderr
    assert "wrote" in result.stdout


def test_versions_stays_exempt_and_ignores_settings_resolution():
    result = _run("versions", settings_env=None)

    assert "DJANGO_SETTINGS_MODULE is not set" not in result.stderr
