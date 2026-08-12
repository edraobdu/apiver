"""Tests for check_version_scheme (ticket #66, ADR 0008 item 3): validates
`APIVER_VERSION_SCHEME` names one of apiver's three built-in Schemes,
mirroring check_version_layout's settings-validation idiom
(test_directory_layout_check.py)."""

from django.core.checks import Error
from django.core.checks.registry import registry
from django.test import override_settings

from apiver.drf import check_version_scheme


def test_an_unset_scheme_produces_no_messages():
    # tests/settings.py never sets APIVER_VERSION_SCHEME — unset defaults to
    # "sequential" (ADR 0008 Consequences' zero-migration guarantee), a
    # valid value, not an error.
    assert check_version_scheme() == []


def test_each_built_in_scheme_name_produces_no_messages():
    for name in ("sequential", "semver", "date"):
        with override_settings(APIVER_VERSION_SCHEME=name):
            assert check_version_scheme() == []


def test_an_unrecognized_scheme_name_reports_an_error():
    with override_settings(APIVER_VERSION_SCHEME="bogus"):
        messages = check_version_scheme()

    assert len(messages) == 1
    assert messages[0].id == "apiver.E009"
    assert "bogus" in messages[0].msg


def test_all_messages_are_errors():
    with override_settings(APIVER_VERSION_SCHEME="bogus"):
        messages = check_version_scheme()

    assert all(isinstance(message, Error) for message in messages)


def test_the_check_is_registered_with_djangos_check_framework():
    assert check_version_scheme in registry.registered_checks
