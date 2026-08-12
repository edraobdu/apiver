"""Unit tests for the Scheme concept (ticket #66, ADR 0008): validate a
Slug's shape, format it into a Display Name, and order Slugs chronologically
— independent of Django, since `apiver versions` reads these with no
DJANGO_SETTINGS_MODULE set (versions_report.py)."""

import pytest

from apiver.schemes import (
    DATE,
    DEFAULT_SCHEME_NAME,
    SCHEME_NAMES,
    SEMVER,
    SEQUENTIAL,
    UnknownSchemeError,
    get_scheme,
)

# --- sequential ---


@pytest.mark.parametrize("slug", ["v1", "v2", "v42"])
def test_sequential_validates_its_base_grammar(slug):
    assert SEQUENTIAL.validate(slug) is True


@pytest.mark.parametrize("slug", ["v1_2_3", "d2026_08_11", "v", "1", "va", "v1.2", "v-1"])
def test_sequential_rejects_shapes_it_does_not_own(slug):
    assert SEQUENTIAL.validate(slug) is False


def test_sequential_format_is_the_identity_function():
    assert SEQUENTIAL.format("v1") == "v1"


def test_sequential_validates_a_label_suffixed_slug():
    assert SEQUENTIAL.validate("v1_testing") is True


def test_sequential_formats_a_label_suffixed_slug_with_a_dash():
    assert SEQUENTIAL.format("v1_testing") == "v1-testing"


def test_sequential_format_raises_for_a_non_conforming_slug():
    with pytest.raises(ValueError):
        SEQUENTIAL.format("v1_2_3")


def test_sequential_compare_orders_chronologically():
    assert SEQUENTIAL.compare("v1", "v2") < 0
    assert SEQUENTIAL.compare("v2", "v1") > 0
    assert SEQUENTIAL.compare("v1", "v1") == 0


def test_sequential_compare_treats_double_digits_numerically_not_lexically():
    assert SEQUENTIAL.compare("v2", "v10") < 0


# --- semver ---


@pytest.mark.parametrize("slug", ["v1_2_3", "v0_0_1", "v10_20_30"])
def test_semver_validates_its_base_grammar(slug):
    assert SEMVER.validate(slug) is True


@pytest.mark.parametrize("slug", ["v1", "v1.2.3", "v1_2", "d2026_08_11", "v1_2_3_4"])
def test_semver_rejects_shapes_it_does_not_own(slug):
    assert SEMVER.validate(slug) is False


def test_semver_format_substitutes_dots_for_underscores():
    assert SEMVER.format("v1_2_3") == "v1.2.3"


def test_semver_validates_a_label_suffixed_slug():
    assert SEMVER.validate("v1_2_3_testing") is True


def test_semver_formats_a_label_suffixed_slug_with_a_dash():
    assert SEMVER.format("v1_2_3_testing") == "v1.2.3-testing"


def test_semver_compare_orders_chronologically_by_major_minor_patch():
    assert SEMVER.compare("v1_2_3", "v1_10_0") < 0
    assert SEMVER.compare("v1_10_0", "v1_2_3") > 0
    assert SEMVER.compare("v1_2_3", "v2_0_0") < 0
    assert SEMVER.compare("v1_2_3", "v1_2_3") == 0


# --- date ---


@pytest.mark.parametrize("slug", ["d2026_08_11", "d2000_01_01"])
def test_date_validates_its_base_grammar(slug):
    assert DATE.validate(slug) is True


@pytest.mark.parametrize("slug", ["2026_08_11", "d2026-08-11", "v1", "d2026_8_11"])
def test_date_rejects_shapes_it_does_not_own(slug):
    assert DATE.validate(slug) is False


def test_date_format_renders_iso_style():
    assert DATE.format("d2026_08_11") == "2026-08-11"


def test_date_validates_a_label_suffixed_slug():
    assert DATE.validate("d2026_08_11_testing") is True


def test_date_formats_a_label_suffixed_slug_with_a_dash():
    assert DATE.format("d2026_08_11_testing") == "2026-08-11-testing"


def test_date_compare_orders_chronologically():
    assert DATE.compare("d2026_08_11", "d2026_08_12") < 0
    assert DATE.compare("d2025_12_31", "d2026_01_01") < 0


# --- label suffix, ADR items 4/6: excluded from strict ordering, sorts
# --- alongside its base point rather than being forced into the timeline.


def test_a_label_suffixed_slug_sorts_alongside_its_base_point_not_after_a_later_one():
    # v1_testing derived from v1 must not be forced later than v2 just
    # because a Label is attached (ADR item 6: composition order and
    # chronological order are independent).
    assert SEQUENTIAL.compare("v1_testing", "v2") < 0
    assert SEQUENTIAL.compare("v2", "v1_testing") > 0


def test_a_bare_base_sorts_before_its_own_label_variant():
    assert SEQUENTIAL.compare("v1", "v1_testing") < 0
    assert SEQUENTIAL.compare("v1_testing", "v1") > 0


def test_compare_is_a_total_order_usable_with_sorted():
    from functools import cmp_to_key

    slugs = ["v2", "v1_testing", "v1", "v10"]
    assert sorted(slugs, key=cmp_to_key(SEQUENTIAL.compare)) == ["v1", "v1_testing", "v2", "v10"]


# --- registry ---


def test_get_scheme_returns_the_named_scheme():
    assert get_scheme("sequential") is SEQUENTIAL
    assert get_scheme("semver") is SEMVER
    assert get_scheme("date") is DATE


def test_get_scheme_raises_for_an_unrecognized_name():
    with pytest.raises(UnknownSchemeError):
        get_scheme("bogus")


def test_default_scheme_name_is_sequential():
    assert DEFAULT_SCHEME_NAME == "sequential"


def test_scheme_names_lists_all_three_built_ins():
    assert set(SCHEME_NAMES) == {"sequential", "semver", "date"}
