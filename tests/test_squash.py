"""`apiver squash` (ticket #77, ADR 0009): flattening a Version's whole
ancestor chain into its own standalone, parentless registry.py.

`tests/fixtures_squash/api/` is a real v1 <- v2 <- v3 chain built from
`tests.testapp.views`' already-existing classes (v1: ping+payments, v2:
overrides payments + adds refunds fresh, v3: overrides payments again and
removes ping) — `apiver squash v3` should absorb v1 and v2, leaving v3 with
every route explicit and no parent. `dirty_base`/`dirty_child` is a second,
deliberately-invalid chain used to exercise preflight refusal.
"""

import pytest
from django.test import override_settings

from apiver.drf import Version
from apiver.drf.squash import SquashError, _registrations_by_key, _render_registry, squash_version
from tests.testapp.views import PaymentViewSet

ROOT_DIR = "tests.fixtures_squash.api"


@pytest.fixture(autouse=True)
def _use_squash_settings():
    with override_settings(
        APIVER_ROOT_DIR=ROOT_DIR,
        APIVER_ROOT_PREFIX="api/",
        APIVER_VERSIONS=["v1", "v2", "v3"],
    ):
        yield


@pytest.fixture
def _restore_v3_registry():
    import tests.fixtures_squash.api.v3.registry as v3_module

    registry_path = v3_module.__file__
    original_source = open(registry_path, encoding="utf-8").read()
    yield
    with open(registry_path, "w", encoding="utf-8") as handle:
        handle.write(original_source)


def test_squash_flattens_the_whole_ancestor_chain(_restore_v3_registry):
    result = squash_version("v3")

    assert result.target == "v3"
    assert result.absorbed == ["v1", "v2"]
    assert result.registry_path.name == "registry.py"
    assert "v3" in str(result.registry_path)


def test_squashed_output_has_no_parent(_restore_v3_registry):
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3 = Version('v3')" in source
    assert ".derive(" not in source


def test_squashed_output_drops_a_removed_route(_restore_v3_registry):
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "'ping'" not in source
    assert "PingViewSet" not in source


def test_squashed_output_keeps_the_targets_own_override(_restore_v3_registry):
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3.register('payments', PaymentViewSetV3, basename='payments')" in source
    assert "PaymentViewSetV3" in source


def test_squashed_output_absorbs_an_inherited_unchanged_registration(_restore_v3_registry):
    """'refunds' was registered fresh on v2 and never touched by v3 — after
    squash it must appear as a plain register() on v3 itself, imported
    straight from tests.testapp.views (never from v2, which is gone from
    the chain)."""
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3.register('refunds', RefundViewSetV2, basename='refunds')" in source
    assert "from tests.testapp.views import" in source
    assert "RefundViewSetV2" in source.split("from tests.testapp.views import", 1)[1].split("\n", 1)[0]


def test_squashed_output_wires_schema_and_docs_via_the_target(_restore_v3_registry):
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3.register('schema/', v3.schema_view(prefix='api/v3/'), name='schema')" in source
    assert "v3.register('docs/', v3.docs_view(), name='docs')" in source


def test_schema_registration_is_emitted_last(_restore_v3_registry):
    result = squash_version("v3")
    source = result.registry_path.read_text()

    schema_index = source.index("v3.register('schema/'")
    payments_index = source.index("v3.register('payments'")
    refunds_index = source.index("v3.register('refunds'")
    assert payments_index < schema_index
    assert refunds_index < schema_index


def test_squash_refuses_a_version_with_no_parent():
    with pytest.raises(SquashError, match="Base Version"):
        squash_version("v1")


def test_squash_refuses_and_writes_nothing_when_an_absorbed_version_is_dirty():
    import tests.fixtures_squash.api.dirty_child.registry as dirty_child_module

    before = open(dirty_child_module.__file__, encoding="utf-8").read()

    with pytest.raises(SquashError) as excinfo:
        squash_version("dirty_child")

    message = str(excinfo.value)
    assert "dirty_base" in message
    assert "InlineInDirtyBase" in message
    assert "stray.py" in message

    after = open(dirty_child_module.__file__, encoding="utf-8").read()
    assert before == after


def test_render_registry_preserves_a_frozen_target():
    target = Version("standalone")
    target.register("payments", PaymentViewSet, basename="payments")
    target.freeze()

    source = _render_registry(target, _registrations_by_key(target), mount_prefix="api/standalone/")

    assert "standalone.freeze()" in source


def test_render_registry_preserves_a_deprecated_target():
    from datetime import UTC, datetime

    sunset = datetime(2030, 1, 1, tzinfo=UTC)
    target = Version("standalone")
    target.register("payments", PaymentViewSet, basename="payments")
    target.deprecate(sunset=sunset)

    source = _render_registry(target, _registrations_by_key(target), mount_prefix="api/standalone/")

    assert "from datetime import datetime" in source
    assert f"standalone.deprecate(sunset=datetime.fromisoformat({sunset.isoformat()!r}))" in source
