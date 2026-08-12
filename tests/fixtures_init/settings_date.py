"""Same project as settings.py, with APIVER_VERSION_SCHEME=date —
scheme-conformance tests (ticket #67, ADR 0008 item 5). The date-shaped
base version name ("d2026_08_11") is passed as `apiver init --base
d2026_08_11` by the tests that use this settings module, not set here
(ticket #86).
"""

from tests.fixtures_init.settings import *  # noqa: F403

APIVER_VERSION_SCHEME = "date"
# init folds a manifest write into itself, reading APIVER_VERSIONS back —
# it must name the same base version the test's `--base` flag passes.
APIVER_VERSIONS = ["d2026_08_11"]
