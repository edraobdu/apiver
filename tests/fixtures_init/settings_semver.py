"""Same project as settings.py, with a semver-shaped APIVER_BASE_VERSION and
APIVER_VERSION_SCHEME=semver — scheme-conformance tests (ticket #67, ADR
0008 item 5) for `apiver init`'s base-version validation and the Display
Name it now uses in the generated URL text.
"""

from tests.fixtures_init.settings import *  # noqa: F403

APIVER_BASE_VERSION = "v1_0_0"
APIVER_VERSION_SCHEME = "semver"
# init folds a manifest write into itself, reading APIVER_VERSIONS back —
# it must name the same base version this file just overrode above.
APIVER_VERSIONS = ["v1_0_0"]
