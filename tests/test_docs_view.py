"""`Version.docs_view()`/`schema_route_name` (ticket 22) — the same call shape
as `schema_view()`, and the fix for a real bug found while adopting apiver into
a project that keeps its pre-existing schema/docs routes mounted alongside the
newly-versioned ones: two different routes sharing the exact same bare name,
with Django's `reverse()` silently picking one.
"""

import re

import pytest
from rest_framework.test import APIClient

from apiver.drf import Version


@pytest.fixture
def client():
    return APIClient()


def test_schema_route_name_is_flat_for_the_base_version():
    assert Version("v9").schema_route_name == "v9-schema"


def test_schema_route_name_is_bare_for_a_derived_version():
    base = Version("v9")
    derived = base.derive("v10")

    assert derived.schema_route_name == "schema"


@pytest.mark.urls("tests.testapp.docs_urls")
@pytest.mark.parametrize(
    ("docs_path", "expected_schema_path"),
    [
        ("/api/docs-v1/docs/", "/api/docs-v1/schema/"),
        ("/api/docs-v2/docs/", "/api/docs-v2/schema/"),
    ],
)
def test_docs_view_resolves_to_its_own_versions_schema(client, docs_path, expected_schema_path):
    """The Base Version (docs-v1, no Django instance namespace) needs its
    schema route's name explicitly qualified to stay reversible; a derived
    Version (docs-v2, namespaced) needs the opposite — the plain local name,
    reversed through its own namespace. Both wired through `.register()`,
    matching exactly what `apiver migrate` generates and what a hand-authored
    version's `registry.py` should write (docs/getting-started.md)."""
    response = client.get(docs_path)

    assert response.status_code == 200
    body = response.content.decode()
    match = re.search(r"url:\s*['\"]([^'\"]+)['\"]", body)
    assert match is not None
    # The swagger_ui.html template renders inside a <script> block, where
    # Django's autoescaping renders "-" as its JS unicode escape.
    assert match.group(1).replace("\\u002D", "-") == expected_schema_path
