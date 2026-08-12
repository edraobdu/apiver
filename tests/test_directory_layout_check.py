from django.core.checks import Error
from django.core.checks.registry import registry
from django.test import override_settings

from apiver.drf import check_version_layout


def test_a_version_root_with_registry_py_produces_no_messages():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["valid_authored"],
    ):
        assert check_version_layout() == []


def test_a_version_root_missing_registry_reports_an_error():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["missing_registry"],
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E002"
    assert "registry.py" in messages[0].msg
    assert "'missing_registry'" in messages[0].msg


def test_a_version_root_with_a_subpackage_reports_an_error():
    """ADR 0003's ticket #77 amendment: a version's root may hold nothing
    besides registry.py — not even a subpackage, which this fixture still
    carries from before that amendment (serializers.py/views.py/payments/)."""
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["subpackaged"],
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E010"
    assert "'subpackaged'" in messages[0].msg


def test_extra_entries_are_listed_by_name():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["subpackaged"],
    ):
        messages = check_version_layout()

    assert "payments" in messages[0].msg
    assert "serializers.py" in messages[0].msg
    assert "views.py" in messages[0].msg


def test_a_registry_with_an_inline_class_definition_reports_an_error():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["inline_definitions"],
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E011"
    assert "InlineWidgetView" in messages[0].msg


def test_the_base_version_root_only_needs_registry_py():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["valid_base"],
    ):
        assert check_version_layout() == []


def test_a_version_root_that_fails_to_import_reports_an_error():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["does_not_exist"],
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E001"


def test_a_version_root_that_is_a_module_not_a_package_reports_an_error():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["not_a_package"],
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E001"


def test_multiple_version_roots_are_each_checked_independently():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["valid_base", "missing_registry"],
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert "'missing_registry'" in messages[0].msg


def test_no_versions_configured_produces_no_messages():
    with override_settings(APIVER_ROOT_DIR="tests.fixtures_layout", APIVER_VERSIONS=[]):
        assert check_version_layout() == []


def test_versions_configured_without_a_root_dir_resolves_the_default_root_dir():
    # APIVER_ROOT_DIR unset falls back to "apiversions" (ADR 0003's ticket #77
    # amendment) rather than erroring — "apiversions.valid_base" doesn't exist
    # in this test project, so it still reports an error, but apiver.E001
    # (import failure), never the removed "root dir unset" apiver.E006.
    with override_settings(APIVER_ROOT_DIR=None, APIVER_VERSIONS=["valid_base"]):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E001"


def test_all_messages_are_errors():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["missing_registry"],
    ):
        messages = check_version_layout()

    assert all(isinstance(message, Error) for message in messages)


def test_the_check_is_registered_with_djangos_check_framework():
    assert check_version_layout in registry.registered_checks
