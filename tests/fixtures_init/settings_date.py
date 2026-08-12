"""Same project as settings.py, with a date-shaped APIVER_BASE_VERSION and
APIVER_VERSION_SCHEME=date — scheme-conformance tests (ticket #67, ADR
0008 item 5).
"""

from tests.fixtures_init.settings import *  # noqa: F403

APIVER_BASE_VERSION = "d2026_08_11"
APIVER_VERSION_SCHEME = "date"
# init folds a manifest write into itself, reading APIVER_VERSIONS back —
# it must name the same base version this file just overrode above.
APIVER_VERSIONS = ["d2026_08_11"]
