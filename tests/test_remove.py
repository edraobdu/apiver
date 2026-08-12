"""`apiver remove` (ticket #84): archiving a squashed-away version — cutting
every direct child's parent link (each becoming its own independent Base
Version) and dropping the archived version's mount from the Aggregation
Root.

`tests/fixtures_remove/api/` holds several small, independent chains:
- v1 (deprecated) <- v2 (already squashed by hand) — the main happy path.
- v10 (deprecated) branching into v11/v12 (both already squashed) — more
  than one direct child.
- v20 (deprecated) <- v21 (never squashed) — precondition refusal.
- v30 (never deprecated) <- v31 (already squashed) — the --force guardrail.
- v40 (deprecated), a leaf with no children at all.
"""

from pathlib import Path

import pytest
from django.test import override_settings

from apiver.drf.remove import RemoveError, remove_version

ROOT_DIR = "tests.fixtures_remove.api"
API_DIR = Path("tests/fixtures_remove/api")


@pytest.fixture(autouse=True)
def _use_remove_settings():
    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_ROOT_PREFIX="api/",
        APIVER_VERSIONS=["v1", "v2", "v10", "v11", "v12", "v20", "v21", "v30", "v31", "v40"],
    ):
        yield


@pytest.fixture
def _restore_fixture_files():
    import tests.fixtures_remove.api.urls as urls_module
    import tests.fixtures_remove.api.v2.registry as v2_module
    import tests.fixtures_remove.api.v11.registry as v11_module
    import tests.fixtures_remove.api.v12.registry as v12_module
    import tests.fixtures_remove.api.v31.registry as v31_module

    paths = [
        urls_module.__file__,
        v2_module.__file__,
        v11_module.__file__,
        v12_module.__file__,
        v31_module.__file__,
    ]
    originals = {path: open(path, encoding="utf-8").read() for path in paths}
    yield
    for path, original in originals.items():
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(original)


def test_remove_cuts_the_only_childs_parent_link(_restore_fixture_files):
    result = remove_version("v1")

    assert result.target == "v1"
    assert result.children == ["v2"]
    assert len(result.registry_paths) == 1
    assert result.registry_paths[0].name == "registry.py"
    assert "v2" in str(result.registry_paths[0])
    assert result.aggregation_path.name == "urls.py"


def test_remove_rewrites_the_childs_registry_as_a_standalone_base_version(_restore_fixture_files):
    remove_version("v1")

    source = API_DIR.joinpath("v2", "registry.py").read_text()
    assert "v2 = Version('v2')" in source
    assert ".derive(" not in source
    assert "from tests.fixtures_remove.api.v1.registry import v1" not in source
    assert "from apiver.drf import Version" in source
    assert ".override(" not in source
    assert "v2.register('payments', PaymentViewSetV2, basename='payments')" in source
    assert "v2.register('schema/', v2.schema_view(prefix='api/v2/'), name='schema')" in source
    assert "v2.register('docs/', v2.docs_view(), name='docs')" in source


def test_remove_drops_the_targets_mount_from_the_aggregation_root(_restore_fixture_files):
    remove_version("v1")

    source = API_DIR.joinpath("urls.py").read_text()
    assert "v1.registry" not in source
    assert "include(v1.urls)" not in source
    # everything else untouched
    assert "v2.registry" in source
    assert "include(v2.urls)" in source


def test_remove_handles_a_branch_into_multiple_children(_restore_fixture_files):
    result = remove_version("v10")

    assert sorted(result.children) == ["v11", "v12"]
    assert len(result.registry_paths) == 2

    v11_source = API_DIR.joinpath("v11", "registry.py").read_text()
    v12_source = API_DIR.joinpath("v12", "registry.py").read_text()
    assert "v11 = Version('v11')" in v11_source
    assert "v12 = Version('v12')" in v12_source
    assert ".derive(" not in v11_source
    assert ".derive(" not in v12_source


def test_remove_handles_a_leaf_with_no_children(_restore_fixture_files):
    result = remove_version("v40")

    assert result.children == []
    assert result.registry_paths == []
    source = API_DIR.joinpath("urls.py").read_text()
    assert "v40" not in source


def test_remove_refuses_and_writes_nothing_when_a_child_was_never_squashed(_restore_fixture_files):
    aggregation_before = API_DIR.joinpath("urls.py").read_text()

    with pytest.raises(RemoveError) as excinfo:
        remove_version("v20")

    message = str(excinfo.value)
    assert "v21" in message
    assert "apiver squash v21" in message

    aggregation_after = API_DIR.joinpath("urls.py").read_text()
    assert aggregation_before == aggregation_after


def test_remove_refuses_a_version_that_was_never_deprecated(_restore_fixture_files):
    with pytest.raises(RemoveError, match="never deprecated"):
        remove_version("v30")


def test_remove_force_archives_a_never_deprecated_version(_restore_fixture_files):
    result = remove_version("v30", force=True)

    assert result.children == ["v31"]
