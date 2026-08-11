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

## 3. Run `apiver migrate`

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

Point the project's *actual* root `urls.py` at the Aggregation Root by appending one `include()` —
adoption is additive, not a restructuring. Every route the project served before `migrate` ran keeps
serving, at exactly the paths it always has; nothing above this new line moves, and nothing needs to
change to keep working:

```python
# config/urls.py — everything already here stays exactly as it was
urlpatterns = [
    path("api/users/", include("users.urls")),
    # ...however much pre-existing routing the project already had...

    # apiver's Aggregation Root (ADR 0007 item 2), appended, not substituted:
    path("", include("api.urls")),
]
```

The *new* surface this adds lives at `/api/v1/...` — the same handlers, reachable a second way,
under a name. Nothing forces the old, unversioned paths to go away: adopting apiver is the moment a
version gets a name, not the moment old clients get broken. Retiring the unversioned paths (if a
project wants to at all) is a separate, deliberate decision the developer makes on their own
timeline — not a side effect of running `migrate`.

### If the project has its own drf-spectacular schema/docs views

If the pre-existing project already serves its own `SpectacularAPIView`/`SpectacularSwaggerView`
(most do) and stays mounted per the additive model above, expect one specific, easy-to-miss
collision: the Base Version deliberately reuses *bare*, unnamespaced route names — including
whatever the pre-existing schema/docs views were named — so that anything elsewhere in the project
already reversing those names by their old, pre-apiver identity keeps resolving (ADR 0001 item 4).
Kept side by side with the pre-existing routes of the *same* names, this is an actual collision, not
just redundancy: Django's `reverse()` for an unqualified name matches the last-registered pattern,
so the pre-existing docs page can silently start rendering `migrate`'s newly-adopted schema instead
of its own — same HTTP status either way, wrong body. Only routes that actually get `reverse()`d at
request time surface this (in practice: just the schema and docs routes); rename the newly-generated
ones in `registry.py` to something distinct, and re-point the docs view's `url_name` at the new name:

```python
# api/v1/registry.py — hand-edited after migrate generated it
v1.register('docs/', SpectacularSwaggerView.as_view(url_name='v1-schema'), name='v1-docs')
...
v1.register('schema/', v1.schema_view(prefix='api/v1/'), name='v1-schema')
```

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

## 4. Verify the base version

```console
$ DJANGO_SETTINGS_MODULE=config.settings python manage.py check
$ DJANGO_SETTINGS_MODULE=config.settings python manage.py test   # or pytest
```

`manage.py check` runs apiver's own system checks — a mis-shaped version directory or a stale
manifest surfaces here, not at request time.

## 5. Author a second version

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

## 6. Mount the new version

```console
$ DJANGO_SETTINGS_MODULE=config.settings apiver mount v2
```

Appends `v2`'s `include()` to the Aggregation Root, at `APIVER_ROOT_PREFIX + "v2/"`. `mount` never
touches `settings.py` — add the new name to `APIVER_VERSIONS` by hand:

```python
APIVER_VERSIONS = ["v1", "v2"]
```

## 7. Verify again

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
- **The root package didn't exist yet before `migrate` could write into it.** `_resolve_target_dir`
  only ever imported the *parent* of the path it was about to create, so a brand-new adoption's
  `APIVER_ROOT_DIR` package didn't exist yet by definition, and the resulting
  `ModuleNotFoundError: No module named 'api'` pointed at the right name but not at the right fix. A
  developer adopting apiver should never have to `mkdir`/`touch __init__.py` themselves before the one
  command whose entire job is adopting their project — **fixed in the library**: `migrate` and `mount`
  now create `APIVER_ROOT_DIR`'s own package on disk if it isn't there yet
  (`_ensure_root_dir_exists`), with a regression test proving it against a project that has never run
  apiver at all.
- **The bare `apiver` CLI needs `PYTHONPATH` set explicitly.** `manage.py` sets
  `DJANGO_SETTINGS_MODULE` for you via `os.environ.setdefault`, which papers over the fact that
  Django itself never puts the project root on `sys.path` — `manage.py` works anyway because it's
  invoked *from* the project root, which Python already adds for a directly-executed script. The
  `apiver` entry point is installed into `.venv/bin` and has no equivalent trick, so
  `ModuleNotFoundError: No module named 'config'` is the first thing anyone doing this for the first
  time will see.
- **The first instinct is to over-adopt.** The first pass at this guide had the project's root
  `urls.py` replaced wholesale with a single `include()`, on the reasoning that the versioned surface
  should be the *only* surface going forward — which meant rewriting every existing test's hard-coded
  path for no reason a real adoption would ever require. Corrected: `migrate` is additive. It doesn't
  move, replace, or deprecate anything that already works; it adds a second, versioned way to reach
  the same handlers, appended to the existing root `urls.py` rather than substituted for it.
  `reference/`'s own pre-existing tests needed zero changes as a result.
- **...but additive isn't automatically collision-free.** Keeping the pre-existing routes mounted
  alongside the newly-adopted ones surfaced a real, silent bug: the Base Version's bare route names
  (chosen so anything already reversing them by their old identity keeps working, ADR 0001 item 4)
  collided with the pre-existing project's own identically-named `schema`/`docs` routes, and Django's
  `reverse()` picked the new one — same HTTP status, silently wrong body. Caught only by asserting the
  actual embedded target URL, not just that the page rendered. Fixed by hand-renaming the newly
  generated routes (see "If the project has its own drf-spectacular schema/docs views" above), with a
  test locking in the correct target for all three docs pages (old, v1, v2).
- **The version-suffix rule has no "but it didn't actually change" exception**, and this surfaces in
  two non-obvious places: overriding the *inherited* schema/docs routes (which need `override()`,
  since `migrate` already registered them on the Base Version), and re-registering a handler at a new
  key with identical behavior (a URL-prefix move) or a third-party class this project doesn't own
  (`SpectacularSwaggerView`). Both need a trivial version-suffixed subclass purely to satisfy the
  rule — now called out explicitly in step 5 above rather than left to the (accurate, but easy to
  read as "did I do something wrong?") `ValueError` message.
- **A `SerializerMethodField` with no return-type hint degrades drf-spectacular's schema to an opaque
  `string`.** Not an apiver behavior at all — plain drf-spectacular — but relevant here because this
  project doubles as the schema-correctness demo: a restructured nested field (catalogue row 9)
  deserves a real object schema, not `string`, so `api/v2/serializers.py`'s `get_card` carries an
  `@extend_schema_field` decorator pointing at a small, unregistered `Serializer` used only for its
  shape.
</content>
