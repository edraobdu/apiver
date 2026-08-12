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


def test_a_version_root_with_a_subpackage_produces_no_messages():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["subpackaged"],
    ):
        assert check_version_layout() == []


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


def test_versions_configured_without_a_root_dir_reports_an_error():
    with override_settings(APIVER_ROOT_DIR=None, APIVER_VERSIONS=["valid_base"]):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E006"


def test_all_messages_are_errors():
    with override_settings(
        APIVER_ROOT_DIR="tests.fixtures_layout",
        APIVER_VERSIONS=["missing_registry"],
    ):
        messages = check_version_layout()

    assert all(isinstance(message, Error) for message in messages)


def test_the_check_is_registered_with_djangos_check_framework():
    assert check_version_layout in registry.registered_checks
