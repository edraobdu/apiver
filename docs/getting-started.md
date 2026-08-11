# Getting started: adopting apiver into an existing project

This walks a project that already has a working DRF API through adopting apiver: installing it,
running `apiver migrate` to adopt the existing API as the Base Version, and then authoring and
mounting a second version as a Delta. It was written and then followed verbatim while converting
`reference/` (issue #22) — every step below was actually executed against a real project, not
copied from the design docs.

## Prerequisites

- Django, matching apiver's own supported range (currently `django~=5.2`; a project pinned to a
  newer Django series has to move to 5.2 first, or wait for apiver to widen its constraint —
  there's no workaround at the dependency level).
- Django REST Framework `~=3.18` and drf-spectacular `~=0.30`.
- An existing DRF project whose API is reachable by recursively walking `ROOT_URLCONF` — plain
  `path()` entries, router-registered ViewSets with explicit `basename=`, and at most one
  drf-spectacular `SpectacularAPIView`. (`apiver migrate` refuses to guess about anything it can't
  cleanly classify — see "If migrate refuses" below.)

## 1. Install apiver

Add `apiver` as a dependency. During development against an unreleased version, that means an
editable path dependency; with `uv`:

```toml
# pyproject.toml
[project]
dependencies = [
    "apiver",
    # ...
]

[tool.uv.sources]
apiver = { path = "../apiver", editable = true }
```

Then add `"apiver"` to `INSTALLED_APPS` — required even though apiver has no models or migrations
of its own, because its Django system checks (the layout check, the manifest-freshness check, the
max-live-versions check) only register via `AppConfig.ready()`:

```python
INSTALLED_APPS = [
    ...,
    "apiver",
]
```

## 2. Add the four settings

```python
APIVER_ROOT_DIR = "api"       # dotted path to the package that will hold the aggregation root
                               # and every version's own package
APIVER_ROOT_PREFIX = "api/"   # absolute URL path every version mounts under
APIVER_BASE_VERSION = "v1"    # the name migrate adopts the existing API as
APIVER_VERSIONS = ["v1"]      # plain list of Live version names — a hand-maintained fact,
                               # not derived from anything on disk
```

`APIVER_ROOT_DIR` is a *filesystem* fact (where the generated packages live) and
`APIVER_ROOT_PREFIX` is a *URL* fact (what every version mounts under) — keep them named
distinctly even when, as here, they resolve to the same string (`"api"` vs. `"api/"`).

Nothing here is auto-detected. If the project's existing API doesn't live under
`APIVER_ROOT_PREFIX` already, pass `apiver migrate --prefix <path>` in the next step to say
explicitly which pre-existing routes count as in scope for adoption.

## 3. Create the (empty) root package

`apiver migrate` writes the Base Version's own package for you
(`<APIVER_ROOT_DIR>/<APIVER_BASE_VERSION>/`), but it needs `APIVER_ROOT_DIR` itself to already
exist as an importable package — it only ever resolves a filesystem path by importing the
*parent* of what it's about to write, never the target itself. For a brand-new adoption this means
creating an empty package by hand first:

```console
$ mkdir api && touch api/__init__.py
```

## 4. Run `apiver migrate`

`apiver` is a standalone CLI, not a `manage.py` subcommand, so it needs both
`DJANGO_SETTINGS_MODULE` and the project root on `PYTHONPATH` set explicitly (`manage.py` does the
first for you automatically; nothing does the second for the bare `apiver` entry point):

```console
$ DJANGO_SETTINGS_MODULE=config.settings PYTHONPATH=. apiver migrate
```

This walks the *live, resolved* `ROOT_URLCONF` under `APIVER_ROOT_PREFIX` (or `--prefix`, if
given), and — if every route it finds can be classified — writes two files:

- `<APIVER_ROOT_DIR>/<APIVER_BASE_VERSION>/registry.py` — one `register()` call per discovered
  route, importing the *existing* serializers/views from wherever they already live. Nothing is
  moved. This file is generated exactly once (migrate refuses to overwrite it on a second run) and
  is hand-editable afterwards, the same way `manage.py startapp` boilerplate is.
- `<APIVER_ROOT_DIR>/urls.py` — the **Aggregation Root**: one `include()` per Live version, each
  carrying its own full absolute mount path (`path("api/v1/", include(v1.urls))`). This file, once
  generated, is meant to be extended in place (by a later `apiver mount`), not regenerated.

Point the project's *actual* root `urls.py` at the Aggregation Root, once, and never touch it
again for a version's sake:

```python
# config/urls.py
urlpatterns = [
    path("", include("api.urls")),
    # anything that isn't apiver's concern (admin/, healthz, etc.) stays here too
]
```

**This changes every existing route's URL** — `/api/users/` becomes `/api/v1/users/`, because the
version name is now part of the path. Anything hard-coding the old paths (tests, API clients,
frontend code) needs updating to the new `/api/v1/...` shape. This is the single biggest piece of
adoption friction and is not optional — it's what "an API version" *means* once there's a name in
the URL.

### If migrate refuses

`migrate` fails closed: if any in-scope route can't be classified or regenerated, it writes
*nothing* and reports every offending route at once, not just the first. Common reasons (each
with a specific diagnostic message):

- A ViewSet mounted on a router without explicit `basename=`.
- A route with no importable symbol (a view built inside a closure/decorator without
  `functools.wraps`).
- `re_path()` used instead of `path()`.
- A namespaced `include()`, or `i18n_patterns()` at the root.
- More than one drf-spectacular schema view under the prefix.

Any of these can be registered by hand afterwards instead — `migrate` covers the common case, not
every case.

## 5. Verify the base version

```console
$ DJANGO_SETTINGS_MODULE=config.settings python manage.py check
$ DJANGO_SETTINGS_MODULE=config.settings python manage.py test   # or pytest
```

`manage.py check` runs apiver's own system checks — a mis-shaped version directory or a stale
manifest surfaces here, not at request time.

## 6. Author a second version

An authored (non-base) version is **hand-written**, not generated — `migrate` only ever adopts the
Base Version. Create the flat layout apiver's layout check requires:

```
api/v2/
    __init__.py
    serializers.py   # subclasses of v1's serializers that need to change, named ...V2
    views.py          # subclasses of v1's views/viewsets that need to change, named ...V2
    registry.py       # the Delta: derive from v1, then register()/override()/remove()
```

Class-based handlers registered or overridden on a non-base version must carry the version's name,
uppercased, in their class name (`PaymentSerializerV2`, not `PaymentSerializer`) — apiver enforces
this at `register()`/`override()` time, because drf-spectacular names schema components off
`__class__.__name__` alone, and two versions sharing a bare class name would collide in the
generated schema.

`registry.py` looks like:

```python
from api.v1.registry import v1
from .serializers import PaymentSerializerV2
from .views import PaymentViewSetV2

v2 = v1.derive("v2")
v2.override("payments", PaymentViewSetV2, basename="payments")
v2.remove("legacy-invoices")
v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
```

`override()` replaces a registration's *entire* route set — there's no way to override just one
action and inherit the rest, so a narrower override drops whatever routes the parent's registration
had that the child's doesn't re-declare. `remove()` only stops *this* version (and anything derived
from it) from serving a key; the parent keeps serving it unchanged.

Two things that aren't obvious the first time through:

- **The schema route needs `override()`, not `register()`.** `migrate` already registered `schema/`
  (and `docs/`) on the Base Version, and every authored version inherits both by default — so giving
  v2 its own, correctly-scoped schema document means *replacing* that inherited registration, the
  same as any other changed resource. `register()` would raise ("already registered on … or one of
  its ancestors") since the key already resolves through the parent.
- **Reusing a handler completely unchanged still needs a version-suffixed subclass.** The
  class-name-suffix rule (above) is enforced on every class-based `register()`/`override()` call on
  an authored version, with no exception for "the class didn't actually change" — this bites most
  often when moving a resource's URL (its handler is identical, only the mount key differs) or
  re-registering a third-party class-based view (e.g. drf-spectacular's own `SpectacularSwaggerView`)
  that this project doesn't own and can't rename. The fix is the same either way: a trivial local
  subclass that exists only to carry the suffix, e.g.
  `class SpectacularSwaggerViewV2(SpectacularSwaggerView): pass`.

## 7. Mount the new version

```console
$ DJANGO_SETTINGS_MODULE=config.settings apiver mount v2
```

Appends `v2`'s `include()` to the Aggregation Root, at `APIVER_ROOT_PREFIX + "v2/"`. `mount` never
touches `settings.py` — add the new name to `APIVER_VERSIONS` by hand:

```python
APIVER_VERSIONS = ["v1", "v2"]
```

## 8. Verify again

```console
$ DJANGO_SETTINGS_MODULE=config.settings python manage.py check
$ DJANGO_SETTINGS_MODULE=config.settings apiver manifest
```

`apiver manifest` (also run automatically at the end of `migrate`, but not `mount`) writes
`apiver.toml`, a committed, non-authoritative snapshot of every Live version's resolution table —
useful for `apiver versions`, which prints lineage/frozen/lifecycle/alias state without booting the
project at all.

---

## Friction found while dogfooding this guide (issue #22)

Every one of these was hit for real while converting `reference/`, then fixed in this guide's
wording (not routed around) — per issue #22's instruction to follow the guide verbatim and record
what doesn't work the first time.

- **Django-version mismatch at adoption.** A project pinned ahead of apiver's supported Django
  range fails at dependency resolution with a fairly clear `uv` error, but nothing in apiver itself
  says "check your Django version" up front — now called out in this guide's Prerequisites rather
  than a step someone has to discover by resolver failure.
- **The root package has to exist before `migrate` can write into it.** `_resolve_target_dir` only
  ever imports the *parent* of the path it's about to create, so a brand-new adoption's
  `APIVER_ROOT_DIR` package doesn't exist yet by definition. The error
  (`ModuleNotFoundError: No module named 'api'`) points at the right name but not at the right fix —
  now step 3 above, rather than something only discoverable by reading `migrate`'s source or its
  test fixtures (which pre-create it silently).
- **The bare `apiver` CLI needs `PYTHONPATH` set explicitly.** `manage.py` sets
  `DJANGO_SETTINGS_MODULE` for you via `os.environ.setdefault`, which papers over the fact that
  Django itself never puts the project root on `sys.path` — `manage.py` works anyway because it's
  invoked *from* the project root, which Python already adds for a directly-executed script. The
  `apiver` entry point is installed into `.venv/bin` and has no equivalent trick, so
  `ModuleNotFoundError: No module named 'config'` is the first thing anyone doing this for the first
  time will see.
- **Adoption changes every URL, immediately.** Not a bug, but the single largest mechanical
  consequence of running `migrate` at all: every hard-coded `/api/<resource>/` in tests, clients, or
  frontend code needs to become `/api/v1/<resource>/` in the same pass. Twenty-five tests across five
  files needed this in `reference/`'s case.
- **The version-suffix rule has no "but it didn't actually change" exception**, and this surfaces in
  two non-obvious places: overriding the *inherited* schema/docs routes (which need `override()`,
  since `migrate` already registered them on the Base Version), and re-registering a handler at a new
  key with identical behavior (a URL-prefix move) or a third-party class this project doesn't own
  (`SpectacularSwaggerView`). Both need a trivial version-suffixed subclass purely to satisfy the
  rule — now called out explicitly in step 6 above rather than left to the (accurate, but easy to
  read as "did I do something wrong?") `ValueError` message.
- **A `SerializerMethodField` with no return-type hint degrades drf-spectacular's schema to an opaque
  `string`.** Not an apiver behavior at all — plain drf-spectacular — but relevant here because this
  project doubles as the schema-correctness demo: a restructured nested field (catalogue row 9)
  deserves a real object schema, not `string`, so `api/v2/serializers.py`'s `get_card` carries an
  `@extend_schema_field` decorator pointing at a small, unregistered `Serializer` used only for its
  shape.
</content>
