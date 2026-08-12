"""`apiver squash` (ticket #77, ADR 0009): making a version's own
`registry.py` an explicit, complete list of every route it resolves —
including whatever it only ever inherited implicitly — without touching its
parent link.

`tests/fixtures_squash/api/` is a real v1 <- v2 <- v3 chain built from
`tests.testapp.views`' already-existing classes (v1: ping+payments, v2:
overrides payments + adds refunds fresh, v3: overrides payments again and
removes ping) — `apiver squash v3` should make every route v3 resolves
through v1/v2 an explicit `override()` on v3 itself, while v3 keeps
deriving from v2 exactly as before. `dirty_base`/`dirty_child` is a second,
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


def test_squashed_output_keeps_the_parent_link(_restore_v3_registry):
    """The parent chain is untouched by squash — only `apiver remove`
    (not yet built) cuts it. A register() call for an already-resolvable
    key would raise at import time, so everything must be override()."""
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3 = v2.derive('v3')" in source
    assert "from tests.fixtures_squash.api.v2.registry import v2" in source
    assert ".register(" not in source


def test_squashed_output_re_declares_a_removed_route_explicitly(_restore_v3_registry):
    """v3.remove('ping') doesn't survive full regeneration verbatim, but the
    removal itself must — otherwise the freshly-written file would silently
    resurrect 'ping' from v2/v1, since nothing else in it says it was ever
    removed."""
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3.remove('ping')" in source
    assert "PingViewSet" not in source


def test_squashed_output_keeps_the_targets_own_override(_restore_v3_registry):
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3.override('payments', PaymentViewSetV3, basename='payments')" in source
    assert "PaymentViewSetV3" in source


def test_squashed_output_absorbs_an_inherited_unchanged_registration(_restore_v3_registry):
    """'refunds' was registered fresh on v2 and never touched by v3 — after
    squash it must appear as an explicit override() on v3 itself (v2 still
    resolves it too, so it can't be register()), imported straight from
    tests.testapp.views."""
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3.override('refunds', RefundViewSetV2, basename='refunds')" in source
    assert "from tests.testapp.views import" in source
    assert "RefundViewSetV2" in source.split("from tests.testapp.views import", 1)[1].split("\n", 1)[0]


def test_squashed_output_wires_schema_and_docs_via_the_target(_restore_v3_registry):
    result = squash_version("v3")
    source = result.registry_path.read_text()

    assert "v3.override('schema/', v3.schema_view(prefix='api/v3/'), name='schema')" in source
    assert "v3.override('docs/', v3.docs_view(), name='docs')" in source


def test_schema_registration_is_emitted_last(_restore_v3_registry):
    result = squash_version("v3")
    source = result.registry_path.read_text()

    schema_index = source.index("v3.override('schema/'")
    payments_index = source.index("v3.override('payments'")
    refunds_index = source.index("v3.override('refunds'")
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


def _derived_target(name: str) -> Version:
    base = Version(f"{name}_base")
    base.register("payments", PaymentViewSet, basename="payments")
    return base.derive(name)


def test_render_registry_preserves_a_frozen_target():
    target = _derived_target("frozentarget")
    target.freeze()

    source = _render_registry(
        target,
        _registrations_by_key(target),
        mount_prefix="api/frozentarget/",
        root_dir=ROOT_DIR,
    )

    assert "frozentarget.freeze()" in source


def test_render_registry_preserves_a_deprecated_target():
    from datetime import UTC, datetime

    sunset = datetime(2030, 1, 1, tzinfo=UTC)
    target = _derived_target("deprecatedtarget")
    target.deprecate(sunset=sunset)

    source = _render_registry(
        target,
        _registrations_by_key(target),
        mount_prefix="api/deprecatedtarget/",
        root_dir=ROOT_DIR,
    )

    assert "from datetime import datetime" in source
    assert f"deprecatedtarget.deprecate(sunset=datetime.fromisoformat({sunset.isoformat()!r}))" in source
