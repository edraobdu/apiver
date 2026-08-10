import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle counters live in Django's cache, not the database — plain pytest
    functions get none of TestCase's automatic isolation for it, so without this a
    notifications throttle test could fail depending on what ran before it."""
    cache.clear()
    yield
    cache.clear()
