# apiver

**Define API versions as deltas, not duplicates.**

[![CI](https://github.com/edraobdu/apiver/actions/workflows/ci.yml/badge.svg)](https://github.com/edraobdu/apiver/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/edraobdu/apiver/branch/master/graph/badge.svg)](https://codecov.io/gh/edraobdu/apiver)
[![Docs](https://readthedocs.org/projects/apiver/badge/?version=latest)](https://apiver.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

apiver is a Django REST Framework library for composing complete API versions from deltas. Your
existing code becomes the **base version**, exactly where it already lives; every later version
declares only what changed against its parent, and everything untouched resolves straight through to
the parent's actual handler objects — not copies of them.

> **Status:** pre-1.0 (`0.1.0.dev0`). Everything documented here exists and is covered by tests, but
> nothing has shipped to PyPI yet and the public API can still move before a real `0.1` tag lands. See
> [Status and roadmap](https://apiver.readthedocs.io/#status-and-roadmap) for what that means for you
> today.

**📖 [Full documentation →](https://apiver.readthedocs.io/)**

## The problem

Shipping a breaking API change — drop a field, remove a resource, change a type — without breaking the
clients still calling the old shape has three bad answers today: copy the API into a `v2/` package and
drag the unchanged 95% along with it; reach for DRF's `URLPathVersioning`, which sets `request.version`
and leaves composition as `if request.version == "v2":` branches smeared through the codebase; or reach
for a library — several have flatlined over the years, and none of the maintained ones do real version
composition either.

None of them let you say *"V2 is V1, except payments returns decimal strings and legacy-invoices is
gone"* and get a complete, correctly-documented V2 surface out of it. And none of them require your
project to already be a mess before apiver is worth adopting — however you got here, apiver only needs
to know what your *next* version changes. **[Read the full problem statement →](https://apiver.readthedocs.io/#the-problem)**

## What you get

- **A second complete API surface for the cost of one field.** One `override()` call, and
  `GET /api/v2/users/` still works — V2 never mentioned users, and the other 95% of the surface was
  never touched.
- **Adoption with nothing to reorganize first.** `apiver init` wraps your existing, working project as
  it is — no file moves, no big-bang migration to schedule. The first breaking change is the only time
  you touch apiver again.
- **Deltas that are ordinary, inspectable Python.** An override is a subclass. No DSL, no parallel
  object model, no migration-chain classes to learn — if you can read a Django class hierarchy, you can
  read a delta.
- **Correct per-version OpenAPI, automatically.** Each version's schema document contains exactly its
  own routes — no leakage from siblings, no hand-maintained schema file to keep in sync.
- **Lifecycle clients can actually see.** `v1.deprecate(sunset=...)` emits real `Deprecation`/`Sunset`
  headers and enforces `410 Gone` on the wall clock — no deploy has to land on the date.
- **Tooling that answers "what does v3 actually serve?"** `apiver versions` and a committed
  `apiver.toml` turn that from an archaeology project into a command.
- **An honest boundary, not a hidden one.** Route composition works for anything routable. Schema
  reasoning works only as far as drf-spectacular can see.
  **[More on that boundary →](https://apiver.readthedocs.io/supported/)**

## A taste of it

```python
# api/v1/registry.py — your existing code, untouched
from apiver.drf import Version
from products.views import ProductViewSet

v1 = Version("v1")
v1.register("products", ProductViewSet, basename="products")
```

```python
# api/v2/registry.py — the whole delta
from api.v1.registry import v1
from products.views import ProductViewSetV2

v2 = v1.derive("v2")
v2.override("products", ProductViewSetV2, basename="products")
```

`GET /api/v2/products/` now serves the new shape. Every other route V2 never mentioned still resolves,
unchanged, straight through to V1. **[Walk through the full adoption →](https://apiver.readthedocs.io/getting-started/)**

## Installation

```console
$ uv add apiver
```

or with `pip`:

```console
$ pip install apiver
```

## Requirements

Python 3.12–3.14 · Django ~5.2 · Django REST Framework ~3.18 · drf-spectacular ~0.30

## Learn more

- **[Full documentation](https://apiver.readthedocs.io/)** — the sales pitch, the philosophy, a real
  adoption walkthrough, and every command and setting.
- **[What If...?](https://apiver.readthedocs.io/what-if/)** — the specific objections an adoption
  decision actually raises, answered plainly.
- **[docs/adr/](docs/adr/)** — the architectural decision records behind every non-obvious choice: route
  identity, the public API surface, layout and the manifest, squash feasibility, intra-version
  hyperlinking, field removal, the Aggregation Root, and version schemes.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — development setup, tests, and lint.
