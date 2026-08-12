"""v20's only direct child — deliberately never squashed: `payments`,
`schema/`, and `docs/` all still resolve implicitly through v20, with no
registrations of its own at all. `apiver remove v20` must refuse and write
nothing."""

from tests.fixtures_remove.api.v20.registry import v20

v21 = v20.derive("v21")
