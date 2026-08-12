"""Derives from dirty_base — squashing this should refuse due to
dirty_base's own violations (inline class + a stray extra file), never
because dirty_child itself is dirty."""

from tests.fixtures_squash.api.dirty_base.registry import dirty_base

dirty_child = dirty_base.derive("dirty_child")
