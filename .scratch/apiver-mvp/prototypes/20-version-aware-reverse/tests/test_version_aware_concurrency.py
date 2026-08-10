"""One viewset class object serves every version. Under concurrency, that is the whole
argument for putting the Version on the request rather than anywhere on the class.

`whoami` touches no database, so these run without a db fixture and each thread is just
routing + view dispatch.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.urls("spike.urls")


def _fetch(path):
    return path, APIClient().get(path).data["stamped_on_request"]


def test_interleaved_requests_never_see_each_others_version():
    paths = ["/api/v1/payments/whoami/", "/api/v2/payments/whoami/"] * 60
    expected = {"/api/v1/payments/whoami/": "v1", "/api/v2/payments/whoami/": "v2"}

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(_fetch, paths))

    assert len(results) == 120
    for path, reported in results:
        assert reported == expected[path], f"{path} reported {reported}"


def test_the_class_attribute_alternative_would_have_to_be_mutated_per_request():
    """Why the register-time stamp can't simply be 'moved to dispatch time'.

    There is exactly one class object behind both versions, so making it version-aware
    would mean writing to shared state on every request — the race the test above would
    then catch.
    """
    from spike.v1.registry import v1
    from spike.v2.registry import v2

    v1_cls = v1.resolution_table()["payments"].handler
    v2_cls = v2.resolution_table()["payments"].handler

    assert v1_cls is v2_cls
    assert v1_cls.stamped_at_register == "v1"  # one value, for two versions
