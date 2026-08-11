from django.core.checks import Error
from django.core.checks.registry import registry
from django.test import override_settings

from apiver.drf import check_version_layout


def test_a_fully_shaped_authored_version_root_produces_no_messages():
    with override_settings(
        APIVER_VERSION_ROOTS={"v2": "tests.fixtures_layout.valid_authored"},
        APIVER_BASE_VERSION=None,
    ):
        assert check_version_layout() == []


def test_an_authored_version_root_missing_registry_reports_an_error():
    with override_settings(
        APIVER_VERSION_ROOTS={"v2": "tests.fixtures_layout.missing_registry"},
        APIVER_BASE_VERSION=None,
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E002"
    assert "registry.py" in messages[0].msg
    assert "'v2'" in messages[0].msg


def test_an_authored_version_root_with_a_subpackage_reports_an_error():
    with override_settings(
        APIVER_VERSION_ROOTS={"v2": "tests.fixtures_layout.subpackaged"},
        APIVER_BASE_VERSION=None,
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E003"
    assert "payments" in messages[0].msg


def test_the_base_version_root_only_needs_registry_py():
    with override_settings(
        APIVER_VERSION_ROOTS={"v1": "tests.fixtures_layout.valid_base"},
        APIVER_BASE_VERSION="v1",
    ):
        assert check_version_layout() == []


def test_the_base_version_root_missing_registry_still_reports_an_error():
    with override_settings(
        APIVER_VERSION_ROOTS={"v1": "tests.fixtures_layout.base_missing_registry"},
        APIVER_BASE_VERSION="v1",
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E002"


def test_the_base_version_root_is_exempt_from_the_subpackage_rule():
    with override_settings(
        APIVER_VERSION_ROOTS={"v1": "tests.fixtures_layout.subpackaged"},
        APIVER_BASE_VERSION="v1",
    ):
        assert check_version_layout() == []


def test_a_version_root_that_fails_to_import_reports_an_error():
    with override_settings(
        APIVER_VERSION_ROOTS={"v2": "tests.fixtures_layout.does_not_exist"},
        APIVER_BASE_VERSION=None,
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E001"


def test_a_version_root_that_is_a_module_not_a_package_reports_an_error():
    with override_settings(
        APIVER_VERSION_ROOTS={"v2": "tests.fixtures_layout.not_a_package"},
        APIVER_BASE_VERSION=None,
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E001"


def test_multiple_version_roots_are_each_checked_independently():
    with override_settings(
        APIVER_VERSION_ROOTS={
            "v1": "tests.fixtures_layout.valid_base",
            "v2": "tests.fixtures_layout.missing_registry",
        },
        APIVER_BASE_VERSION="v1",
    ):
        messages = check_version_layout()

    assert len(messages) == 1
    assert "'v2'" in messages[0].msg


def test_no_version_roots_configured_produces_no_messages():
    with override_settings(APIVER_VERSION_ROOTS={}, APIVER_BASE_VERSION=None):
        assert check_version_layout() == []


def test_all_messages_are_errors():
    with override_settings(
        APIVER_VERSION_ROOTS={"v2": "tests.fixtures_layout.missing_registry"},
        APIVER_BASE_VERSION=None,
    ):
        messages = check_version_layout()

    assert all(isinstance(message, Error) for message in messages)


def test_the_check_is_registered_with_djangos_check_framework():
    assert check_version_layout in registry.registered_checks
