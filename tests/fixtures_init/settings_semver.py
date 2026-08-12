"""Same project as settings.py, with APIVER_VERSION_SCHEME=semver —
scheme-conformance tests (ticket #67, ADR 0008 item 5) for `apiver init`'s
base-version validation and the Display Name it now uses in the generated
URL text. The semver-shaped base version name ("v1_0_0") is passed as
`apiver init --base v1_0_0` by the tests that use this settings module, not
set here (ticket #86).
"""

from tests.fixtures_init.settings import *  # noqa: F403

APIVER_VERSION_SCHEME = "semver"
# init folds a manifest write into itself, reading APIVER_VERSIONS back —
# it must name the same base version the test's `--base` flag passes.
APIVER_VERSIONS = ["v1_0_0"]
