"""No parent, no schema Registration — proves `apiver mount` skips the
schema override silently when there is no ancestor to inherit its
key/name from (ticket #47)."""

from apiver.drf import Version

v3 = Version("v3")
