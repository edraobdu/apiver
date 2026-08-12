"""Deliberately violates ADR 0003's ticket #77 rule two ways at once: an
inline class definition here, and a stray extra file (stray.py) sitting in
this version's root. Used to test squash's preflight validation collects
every violation before refusing."""

from apiver.drf import Version


class InlineInDirtyBase:
    pass


dirty_base = Version("dirty_base")
