"""Same project as settings.py, with APIVER_VERSION_SCHEME=semver — used by
scheme-conformance tests (ticket #67, ADR 0008 item 5) that need a
non-sequential scheme configured.
"""

from tests.fixtures_mount.settings import *  # noqa: F403

APIVER_VERSION_SCHEME = "semver"
