# Getting started: adopting apiver into an existing project

Adopt apiver into a project that already has a working DRF API: install it, run `apiver init` to
adopt the existing API as the Base Version, then author and mount a second version. See
[`tutorial.md`](tutorial.md) for this same flow walked file-by-file against a real project
(`reference/`), including a full breaking-change example.

## Prerequisites

- `django~=5.2`, `djangorestframework~=3.18`, `drf-spectacular~=0.30`.
- An API reachable by walking `ROOT_URLCONF`: plain `path()` entries, router-registered ViewSets
  with explicit `basename=`, at most one drf-spectacular `SpectacularAPIView`. `apiver init`
  refuses anything it can't classify — see "If init refuses" below.

## 1. Install apiver

```toml
# pyproject.toml
[project]
dependencies = ["apiver"]

[tool.uv.sources]
apiver = { path = "../apiver", editable = true }  # editable path while unreleased
```

Add `"apiver"` to `INSTALLED_APPS` — it has no models, but its system checks (layout, manifest
freshness, max-live-versions) only register via `AppConfig.ready()`.

```python
INSTALLED_APPS = [..., "apiver"]
```

## 2. Add the four settings

```python
APIVER_ROOT_DIR = "api"          # dotted path to the package holding every version
APIVER_ROOT_PREFIX = "api/"      # absolute URL path every version mounts under
APIVER_BASE_VERSION = "v1"       # the name init adopts the existing API as
APIVER_VERSIONS = ["v1"]         # hand-maintained list of Live version names
```

`APIVER_ROOT_PREFIX` is where the *new* versioned surface will live (`api/v1/`, `api/v2/`, ...) —
not necessarily where the *existing* code lives today. `init` defaults to adopting whatever's
already under `APIVER_ROOT_PREFIX`; if the existing API lives somewhere else (no `/api/` segment,
mixed in with `admin/`, etc.), pass `apiver init --prefix <path>` to say so explicitly. `--prefix`
only controls what gets adopted — it has no effect on where the new surface mounts.

`--prefix` is a single path. A project with routes scattered across several unrelated prefixes
needs one `init` run against the largest tree, then hand-written `register()` calls for the rest
(multi-prefix support: [#61](https://github.com/edraobdu/apiver/issues/61)).

## 3. Run `apiver init`

```console
$ DJANGO_SETTINGS_MODULE=config.settings apiver init
# or: apiver --settings config.settings init
```

Django settings resolve from `--settings`, then `DJANGO_SETTINGS_MODULE`, then
`[tool.apiver].django_settings_module` in `pyproject.toml`. `apiver` isn't a `manage.py`
subcommand, so run it from the project root; it puts the cwd on `sys.path` itself.

This walks `ROOT_URLCONF` under the scope from step 2 and, if every route classifies, writes:

- `<APIVER_ROOT_DIR>/<APIVER_BASE_VERSION>/registry.py` — one `register()` call per discovered
  route, importing the existing views/serializers from wherever they already live. Nothing moves.
  Generated once; hand-editable afterwards.
- `<APIVER_ROOT_DIR>/urls.py` — the **Aggregation Root**: one `include()` per Live version, each
  with its own full mount path. Extended in place by later `apiver mount` calls, never regenerated.

Nothing found under scope is fine too — `init` still produces a route-less Base Version wired with
`schema/`/`docs/`, the same guarantee `mount` gives every later version.

Point the project's real root `urls.py` at the Aggregation Root — one appended `include()`, nothing
else changes:

```python
urlpatterns = [
    path("api/users/", include("users.urls")),
    # ...existing routing, untouched...
    path("", include("api.urls")),
]
```

The new surface lives at `/api/v1/...`, reaching the same handlers a second way. The old,
unversioned paths keep serving exactly as before — retiring them is a separate decision, not a
side effect of `init`.

**Schema/docs get version-qualified names automatically.** If the project already serves its own
`SpectacularAPIView`/`SpectacularSwaggerView` and keeps it mounted (the additive default above),
a bare `schema`/`docs` name on the Base Version would collide with it — Django's `reverse()`
would pick whichever was registered last, silently serving the wrong page. So a discovered schema
view is always named `f"{base_name}-schema"` and a discovered docs view gets its `url_name`
repointed at it, regardless of what they were called before:

```python
# api/v1/registry.py — generated
v1.register("docs/", v1.docs_view(), name="v1-docs")
...
v1.register("schema/", v1.schema_view(prefix="api/v1/"), name="v1-schema")
```

### If init refuses

`init` writes nothing and reports every offending route at once. Common causes:

- A ViewSet mounted without explicit `basename=`.
- A handler with no importable symbol (built in a closure/decorator without `functools.wraps`).
- `re_path()` instead of `path()`.
- A namespaced `include()`, or `i18n_patterns()` at the root.
- More than one drf-spectacular schema view under the prefix.

Register any of these by hand instead — `init` covers the common case, not every case.

## 4. Verify the base version

```console
$ DJANGO_SETTINGS_MODULE=config.settings python manage.py check
$ DJANGO_SETTINGS_MODULE=config.settings python manage.py test   # or pytest
```

`manage.py check` runs apiver's system checks — a mis-shaped version directory or stale manifest
surfaces here, not at request time.

## 5. Mount a second version

Authored versions only ever come from `apiver mount` — never hand-written:

```console
$ DJANGO_SETTINGS_MODULE=config.settings apiver mount v2 --from v1
```

This generates `api/v2/registry.py` from scratch (refuses if it already exists) and appends `v2`
to the Aggregation Root at `APIVER_ROOT_PREFIX + "v2/"`:

```python
from api.v1.registry import v1

v2 = v1.derive("v2")
v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
v2.override("docs/", v2.docs_view(), name="docs")
```

Both use `override()` because `init` always wires `schema/`/`docs/` on the Base Version — `mount`
uses `register()` only when deriving from a version that doesn't already have one.

`mount` never touches `settings.py`; add the new version by hand (its last line of output is a
reminder — skip it and the version simply won't resolve, silently):

```python
APIVER_VERSIONS = ["v1", "v2"]
```

## 6. Add the version's changed endpoints

```
api/v2/
    registry.py      # mount already wrote derive() + schema/docs — add your Delta below
    serializers.py    # changed serializers, named ...V2
    views.py          # changed views/viewsets, named ...V2
```

Every class-based handler registered or overridden on a non-base version must carry the version's
name, uppercased, in its class name (`PaymentSerializerV2`, not `PaymentSerializer`) — enforced at
`register()`/`override()` time, because drf-spectacular names schema components off
`__class__.__name__` alone, and two same-named classes in different versions would collide. This
applies even to a handler that's otherwise unchanged (e.g. only its URL moved, or it's a
third-party class you don't own) — subclass it trivially just to carry the suffix.

```python
from api.v1.registry import v1
from .serializers import PaymentSerializerV2
from .views import PaymentViewSetV2

v2 = v1.derive("v2")
v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
v2.override("docs/", v2.docs_view(), name="docs")
v2.override("payments", PaymentViewSetV2, basename="payments")
v2.remove("legacy-invoices")
```

`override()` replaces the whole registration — no partial override, so a narrower one drops any
parent routes it doesn't re-declare. `remove()` only stops this version (and its descendants) from
serving a key; the parent is unaffected.

A `SerializerMethodField` with no return-type hint shows up in the schema as an opaque `string`;
use `@extend_schema_field(SomeSerializer)` on the method to give it a real shape.

## 7. Verify again

```console
$ DJANGO_SETTINGS_MODULE=config.settings python manage.py check
$ DJANGO_SETTINGS_MODULE=config.settings apiver manifest
```

`apiver manifest` writes `apiver.toml`, a committed snapshot of every Live version's resolution
table, used by `apiver versions` to print lineage/frozen/lifecycle/alias state without booting the
project.

## 8. Naming a stable pointer (optional)

A client-facing name (`stable`, `current`) that should move to a different version later, without
callers changing their URL, is an `Alias`, not another mounted version:

```console
$ DJANGO_SETTINGS_MODULE=config.settings apiver alias stable --from v2
```

Writes no `registry.py` of its own — `Alias.schema_view()`/`docs_view()` proxy straight through to
the target's, so re-pointing it later is a one-line `target=` edit. Like `mount`, never touches
`settings.py`:

```python
APIVER_ALIASES = ["stable"]
```
