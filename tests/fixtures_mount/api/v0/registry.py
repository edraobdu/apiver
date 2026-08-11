"""No schema, no docs, no parent — proves `apiver mount` always wires both
on a version derived from this one, using register() for both since
neither key resolves anywhere in this chain (ticket #47)."""

from apiver.drf import Version

v0 = Version("v0")
