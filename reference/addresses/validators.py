import re

from rest_framework import serializers

# Country-aware, so it can't be expressed as a single declarative regex on the
# field — this is the shape of validation that only shows up as custom
# validate_* logic, and is invisible to a schema diff either way (catalogue
# row 7): the field stays a plain CharField before and after any tightening.
_PATTERNS = {
    "US": re.compile(r"^\d{5}(-\d{4})?$"),
    "CA": re.compile(r"^[A-Za-z]\d[A-Za-z] ?\d[A-Za-z]\d$"),
    "MX": re.compile(r"^\d{5}$"),
}


def validate_postal_code_for_country(postal_code, country):
    pattern = _PATTERNS.get(country)
    if pattern and not pattern.match(postal_code):
        raise serializers.ValidationError(
            f"'{postal_code}' is not a valid postal code for {country}."
        )
