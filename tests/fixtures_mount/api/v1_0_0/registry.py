"""A semver-scheme-conforming pre-authored version — a `--from` source for
scheme-conformance tests (ticket #67, ADR 0008 item 5): `mount` now
validates a newly-authored slug against the configured scheme, so
exercising its happy path under `semver` needs an existing `--from` target
that already conforms.
"""

from apiver.drf import Version

v1_0_0 = Version("v1_0_0")
