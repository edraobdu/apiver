# apiver

**Define API versions as deltas, not duplicates.**

[![CI](https://github.com/edraobdu/apiver/actions/workflows/ci.yml/badge.svg)](https://github.com/edraobdu/apiver/actions/workflows/ci.yml)

apiver is a Django REST Framework library for composing complete API versions from deltas. A **base
version** stays exactly where your existing code already lives; every later **authored version**
declares only what changed against its parent. Everything untouched resolves back through the chain to
the same handler objects the parent already uses — not copies of them — so every version presents a
complete, working API surface without duplicating the 95% of it that didn't change.

> **Status:** pre-1.0 (`0.1.0.dev0`). Everything documented below exists and is tested against a real
> reference project, but nothing has shipped to PyPI yet and the public API can still move before a real
> `0.1` tag lands. See [Roadmap](#roadmap) for what's next, and [Status and stability](#status-and-stability)
> for what that means for you today.

## Table of contents

- [The problem](#the-problem)
- [Philosophy](#philosophy)
- [What you get](#what-you-get)
- [How this compares to Cadwyn](#how-this-compares-to-cadwyn)
- [Quickstart: overriding a field](#quickstart-overriding-a-field)
- [Adopting apiver](#adopting-apiver)
  - [Into an existing project](#into-an-existing-project-the-common-case)
  - [Into a new project](#into-a-new-project)
- [What's supported today](#whats-supported-today)
- [The routing/schema boundary](#the-routingschema-boundary)
- [Lifecycle: deprecation and sunset](#lifecycle-deprecation-and-sunset)
- [Version schemes](#version-schemes)
- [CLI at a glance](#cli-at-a-glance)
- [Settings](#settings)
- [Requirements](#requirements)
- [Installation](#installation)
- [Roadmap](#roadmap)
- [Status and stability](#status-and-stability)
- [Learn more](#learn-more)

## The problem

A Django REST Framework project needs to ship a breaking change — drop a field, remove a resource,
change a type — without breaking the clients still calling the old shape. Every available answer today
is bad in a specific way:

- **Copy the API into a `v2/` package.** The 5% that actually changed drags the other 95% along with
  it. Every later bug fix has to be applied N times, the copies drift silently, and nobody can tell by
  reading the code which parts of V2 are a deliberate change and which are a stale duplicate that nobody
  noticed diverging.
- **Reach for DRF's built-in versioning.** `URLPathVersioning` sets `request.version` and stops there.
  There's no fallback and no composition, so the developer hand-writes `if request.version == "v2":`
  branches scattered through views, serializers and querysets — versioning logic smeared across the
  codebase instead of declared in one place.
- **Reach for a library.** Several DRF versioning packages have flatlined over the years. The one
  actively-maintained alternative that does real version composition, [Cadwyn](https://github.com/zmievsa/cadwyn),
  is FastAPI-only and takes the *inverse* architecture — see [the comparison below](#how-this-compares-to-cadwyn).

None of these give you a way to say *"V2 is V1, except payments returns decimal strings and
legacy-invoices is gone"* and get a **complete, correctly-documented V2 API surface** out of it — nor do
they let you answer, at a glance, months later: what does `v3` actually serve? Which routes does it
inherit rather than define? Is the published OpenAPI document for `v2` still accurate? Did anyone
remember to tell clients `v1` is going away?

## Philosophy

**Messy URL patterns are a symptom, not the disease.** By the time a project has a `views_v2.py`, a
`serializers_v2_actually_final.py`, and three different `if version ==` conditionals guarding the same
queryset, the underlying problem isn't the file layout — it's that nothing in the codebase can say what
changed between versions and what didn't. apiver forces that question to be answered explicitly, once,
at the one place a version's behavior is actually decided: `register()`, `override()`, `remove()`.

**Flexibility is the devil.** DRF and Django are permissive by design, and that permissiveness is
exactly what let messy versioning happen in the first place — there are a dozen ways to branch on
`request.version`, and every one of them is a private, uninspectable decision made inside a method body.
apiver is deliberately narrow instead: three verbs, one direction of inheritance, loud failures on
misuse. `register()` raises on a key that already exists. `override()` raises on a key that doesn't.
Setting a serializer field to `None` — the idiom every Django-forms-trained developer reaches for to
remove a field — raises too, because DRF silently keeps serving it. Nothing about apiver tries to be
flexible enough to accommodate every way a team might want to version an API; it tries to be narrow
enough that there's exactly one obvious way, and it happens to be correct.

**Versioning is a mindset, not a feature you bolt on.** Reaching for `if request.version == "v2":` the
first time a breaking change comes up is a reactive decision, made under deadline pressure, by whoever
happened to touch that view last. apiver asks for the decision up front instead: a version is `Frozen`
or it isn't; it's `Live`, `Deprecated`, `Sunset`, or `Archived`; a route is inherited or it's an explicit
`Delta`. Once that vocabulary exists, versioning stops being a special case scattered through the
codebase and becomes an ordinary fact about the project's structure — visible in `apiver versions`,
committed in `apiver.toml`, reviewable in a diff.

## What you get

- **A complete surface per version.** `GET /api/v2/users/` works even though V2 never mentions users.
- **Deltas that are ordinary, inspectable Python.** An override is a subclass. There's no DSL, no
  parallel object model, no migration-chain classes to learn.
- **Correct per-version OpenAPI.** Each version serves its own schema document containing exactly its
  own routes — no leakage from siblings, no duplicated operations from alias mounts.
- **Loud failures, never silent ones.** Registering an existing key, overriding a nonexistent one,
  mutating a frozen version, the `field = None` footgun — all of it raises at registration time, not at
  3am in production.
- **Lifecycle clients can actually see.** `v1.deprecate(sunset=...)` emits `Deprecation` and `Sunset`
  headers on every response, and returns `410 Gone` once the sunset date passes — enforced on the wall
  clock, so no deploy has to land on the date.
- **Tooling that answers the questions.** `apiver init` scaffolds an existing project's routes into a
  base version without moving a file; `apiver versions` prints what's served where and what's inherited;
  `apiver.toml` is a committed snapshot CI can assert is current.
- **An honest boundary, not a hidden one.** Route composition works for anything routable. Schema
  reasoning works only for what drf-spectacular understands. [More below](#the-routingschema-boundary).

## How this compares to Cadwyn

[Cadwyn](https://github.com/zmievsa/cadwyn) is the other library actually doing real version
composition for a Python API framework, and it's worth naming directly rather than pretending it
doesn't exist. The two projects made opposite architectural bets, and neither replaces the other:

- **Cadwyn is latest-canonical.** You write and maintain one current version; every older version is
  *reconstructed* by applying backward migrations to a request/response as it enters and leaves. Cadwyn
  is FastAPI-only, and the migration-chain model fits FastAPI's request/response-transform style well.
- **apiver is base-canonical, forward-composing.** The base version — your existing code — stays
  authoritative and untouched. Every later version is a genuine, independent set of route registrations
  that happens to inherit whatever it doesn't override. There's no request/response transform step and
  no migration-function chain to write or maintain; a version's behavior is exactly what its Python code
  says, full stop.

If your team thinks in terms of "the current version is truth, older ones are reconstructed from it,"
Cadwyn's model is a more direct fit — and if you're on FastAPI, apiver isn't an option for you today
regardless (see [Roadmap](#roadmap)). If your team thinks in terms of "V1 is what's already running in
production, V2 is a delta against it," apiver is built around exactly that mental model.

## Quickstart: overriding a field

The fastest way to see the whole mechanism is to add one field to one endpoint in a brand-new version.
This is deliberately not tied to any generated file layout — it's the whole idea on one screen. (In a
real project, `apiver mount v2 --from v1` scaffolds this file for you — see
[Adopting apiver](#adopting-apiver) below.)

Start with an ordinary DRF resource — nothing apiver-specific about it yet:

```python
# products/serializers.py, products/views.py — your code, unchanged
from rest_framework import serializers, viewsets


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "price_cents"]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

Declare it as your base version — this is the one-time step that turns "an app" into "an app with a
version":

```python
# api/v1/registry.py
from apiver.drf import Version
from products.views import ProductViewSet

v1 = Version("v1")
v1.register("products", ProductViewSet, basename="products")
```

Now say V2 adds a `discount_price_cents` field to the same resource. `derive()` and `override()` are
the entire delta:

```python
# api/v2/registry.py
from rest_framework import serializers

from api.v1.registry import v1
from products.serializers import ProductSerializer
from products.views import ProductViewSet
from apiver.drf import Version

# Classes registered on a non-base version must carry the version's suffix —
# drf-spectacular names schema components off the class name alone, and apiver
# enforces this at override() time so two same-named classes in different
# versions can never collide silently.


class ProductSerializerV2(ProductSerializer):
    discount_price_cents = serializers.IntegerField(read_only=True)

    class Meta(ProductSerializer.Meta):
        fields = [*ProductSerializer.Meta.fields, "discount_price_cents"]


class ProductViewSetV2(ProductViewSet):
    serializer_class = ProductSerializerV2


v2 = v1.derive("v2")
v2.override("products", ProductViewSetV2, basename="products")
```

Mount both — this is ordinary Django, no namespace to hand-write:

```python
# api/urls.py — the Aggregation Root
from django.urls import include, path

from api.v1.registry import v1
from api.v2.registry import v2

urlpatterns = [
    path("api/v1/", include(v1.urls)),
    path("api/v2/", include(v2.urls)),
]
```

That's the whole change. `GET /api/v2/products/` now returns `discount_price_cents`; `GET
/api/v1/products/` doesn't, and never changed. If `products/` were one endpoint out of thirty, the
other twenty-nine would need zero lines touched — V2 never mentions them, and they'd still resolve,
unchanged, straight through to V1's exact `ProductViewSet` object. That's the whole pitch: one field,
one subclass, one `override()` call, and a second complete API surface exists next to the first one.

## Adopting apiver

### Into an existing project (the common case)

This is the path most teams actually need, and it's the one apiver is built around first: **you have a
working DRF API today, and you want to start versioning it without moving a single file.**

```console
$ uv add apiver   # or your project's usual dependency manager
```

Add `"apiver"` to `INSTALLED_APPS` — it has no models, but its system checks (layout, manifest
freshness, live-version count) only register through `AppConfig.ready()` — and four settings:

```python
APIVER_ROOT_DIR = "api"  # dotted path to the package holding every version
APIVER_ROOT_PREFIX = "api/"  # absolute URL path every version mounts under
APIVER_BASE_VERSION = "v1"  # the name init adopts the existing API as
APIVER_VERSIONS = ["v1"]  # hand-maintained list of live version names
```

Then:

```console
$ apiver init
wrote .../api/v1/registry.py
wrote .../api/urls.py
wrote .../apiver.toml
```

`init` walks your live `ROOT_URLCONF`, classifies every route it finds under the prefix you gave it,
and writes a `registry.py` that imports your **existing** views and serializers exactly where they
already live — one `register()` call per resource. It writes new files; it does not move, rename, or
rewrite a single line of code you already have. Your existing `reverse()` calls, tests, Celery task
paths, and admin registrations keep working untouched, because the modules they point at haven't moved.

From there, breaking a change is `apiver mount v2 --from v1` (scaffolds a new version's `registry.py`,
already wired with its own schema/docs routes) followed by exactly the override shown in the
[quickstart](#quickstart-overriding-a-field) above, for whatever actually changed.

This is deliberately the same walkthrough as the full tutorial, run for real against a working DRF
project with 22 composed routes across seven resources, commands and output included verbatim — see
[**docs/tutorial.md**](docs/tutorial.md) for the whole thing, including the six change-shapes that
are easy to get subtly wrong (field rename, whole-field removal, flat-to-nested restructuring,
`SerializerMethodField` output changes, URL prefix moves, and `@action` removal).

### Into a new project

Nothing above assumes an existing API. `apiver init` scaffolds a route-less base version when it finds
none under the given prefix, and you register your first resources directly on `v1` — there's no delta
to write yet, because a version's very first release has nothing to be a delta *against*. The moment
you need to break something, `apiver mount v2 --from v1` and the same `override()`/`register()`/
`remove()` verbs apply exactly as above.

## What's supported today

Route composition handles anything routable — ViewSets, `APIView`s, function views, plain Django views
— uniformly. Below is the change-shape catalogue apiver's own reference project demonstrates end to
end, including every awkward or schema-invisible case, not just the easy ones:

| Change | How | Visible in a schema diff? |
| --- | --- | --- |
| Add a field | Declare it on the subclassed serializer | Yes |
| Change type, nullability, validation, choices, read-only | Redeclare the field on the subclass | Yes |
| Remove a field | `Meta.fields` surgery against the parent's list | Yes |
| Rename a field | Add the new name, remove the old — no dedicated rename primitive | Yes, as one field deleted and one added |
| Change a `SerializerMethodField`'s output | Override `get_<field>` | **No** — same schema, different response body |
| Flat fields → nested object | Assemble the nested shape in a `SerializerMethodField`, translate writes back by hand | Yes, if annotated with `@extend_schema_field`; opaque otherwise |
| Add a resource | `register()` | Yes |
| Remove a resource | `remove()` | Yes |
| Change a resource's URL prefix | `remove()` the old key, `register()` the same handler at the new one | Yes |
| Remove an `@action` | Set the action attribute to `None` on the subclass | Yes |
| Change permissions, authentication | Override the ordinary DRF class attribute | **No** |
| Change pagination, filtering, default ordering, throttling | Override the ordinary DRF class attribute | **No** |
| Change the error response shape | Override exception handling | **No** |

The field-removal story has one sharp edge worth calling out explicitly: **`field = None` does not
remove a field.** It's the idiom every Django-forms developer reaches for, and DRF silently ignores it —
the field survives in both the response and the schema. apiver walks the MRO at `register()`/
`override()` time and raises if it sees this, pointing at `Meta.fields` surgery instead. The
`@action`-removal idiom is the asymmetric exception: `refund = None` on a ViewSet subclass *does*
correctly remove an inherited `@action` — DRF's own `get_extra_actions()` already handles that cleanly.

The recommended default for removing a field a client still depends on is **deprecate, then remove**:
soften it in `V(n)` with `required=False` and drf-spectacular's native `deprecate_fields`, then
hard-remove it in `V(n+1)`. Immediate hard removal stays the documented fast path for low-stakes fields
nobody's realistically depending on.

## The routing/schema boundary

Stated plainly, because a hidden boundary is worse than an honest one: **route composition works for
anything routable. Schema reasoning works only for what drf-spectacular understands.** A bare `APIView`
with no `serializer_class` routes correctly under every version and does appear in its OpenAPI document
— just with a thin, degraded entry (no request/response body shape) instead of a real one. This isn't a
gap apiver is hiding; it's a property of drf-spectacular's own introspection, and apiver doesn't try to
paper over it with guesswork.

## Lifecycle: deprecation and sunset

A version's lifecycle lives on the `Version` object itself — never in settings, never only in the
manifest — so there's exactly one source of truth:

```python
from datetime import datetime, timezone

v1.deprecate(sunset=datetime(2027, 1, 1, tzinfo=timezone.utc))
```

From that point on, every response `v1` serves carries `Deprecation: true` and `Sunset: <HTTP-date>`
headers. Once the sunset date passes — checked on the wall clock, per request, not baked in at deploy
time — `v1` starts returning `410 Gone` with DRF's ordinary `{"detail": ...}` body instead of reaching
the view. A version stays **Live** (counted, mounted, still answering) through both `Deprecated` and
past-`Sunset` states; it only becomes **Archived** once its mount is actually removed from the URLconf.

A movable, client-facing name — `stable`, `latest` — is a separate concept, an `Alias`, not another
version:

```console
$ apiver alias stable --from v2
```

Re-pointing `stable` at a future `v3` is a one-line `target=` edit in the generated Aggregation Root;
callers of `/api/stable/...` never have to change anything.

## Version schemes

Version names default to plain sequential slugs — `v1`, `v2`, … — and that stays every existing
project's behavior with zero changes. A project can opt into `semver`- or date-shaped names instead via
one project-wide setting:

```python
APIVER_VERSION_SCHEME = "semver"  # or "date"; unset defaults to "sequential"
```

| Scheme | Slug (what you type) | Display Name (what shows up in URLs) |
| --- | --- | --- |
| `sequential` (default) | `v1`, `v2` | same as the slug |
| `semver` | `v1_2_3` | `v1.2.3` |
| `date` | `d2026_08_11` | `2026-08-11` |

`apiver mount`, `apiver init`, and `apiver alias --from` validate every version name against the
configured scheme before writing anything, failing loud on a non-conforming name rather than silently
accepting a typo. The Display Name surfaces in the generated Aggregation Root and
`schema_view(prefix=...)` URL text (e.g. `/api/v1.2.3/`) — the module dotted path, the Django instance
namespace, and the version-suffix class-name check all keep the raw slug unchanged, since a Python
identifier can't contain dots. An optional `_label` suffix (`v1_2_3_testing`) gives a branch or testing
name a legal shape without making it a chronological point. `apiver alias`'s own name is exempt from
scheme validation — it's a human label (`stable`, `latest`), not a version point — but its `--from`
target is still validated as a real, scheme-conforming version. See
[ADR 0008](docs/adr/0008-version-schemes.md) for the full design.

## CLI at a glance

`apiver` is a standalone command, not a `manage.py` subcommand, so it can introspect a project offline.
`init`, `mount`, `alias` and `manifest` need Django settings resolved (`--settings`, then
`DJANGO_SETTINGS_MODULE`, then `[tool.apiver].django_settings_module` in `pyproject.toml`); `versions`
reads only the committed `apiver.toml` and needs neither.

| Command | What it does |
| --- | --- |
| `apiver init [--prefix PATH]` | Adopts an existing project's routes as the base version, or scaffolds a route-less one — moves nothing. |
| `apiver mount NAME --from PARENT` | Scaffolds a new authored version's `registry.py`, derived from `PARENT`, with schema/docs already wired. |
| `apiver alias NAME --from VERSION` | Declares a movable name pointing at an already-mounted version. |
| `apiver manifest [--check]` | Writes `apiver.toml`, a committed snapshot of every version's resolution table; `--check` exits non-zero if it's stale, the same idiom as `makemigrations --check`. |
| `apiver versions` | Prints lineage, frozen status, lifecycle state, alias pointers, and defined-vs-inherited routes per version — reading only the manifest, without booting the project. |

## Settings

| Setting | Purpose |
| --- | --- |
| `APIVER_ROOT_DIR` | Dotted path to the package holding the Aggregation Root and every version's own package. |
| `APIVER_ROOT_PREFIX` | Absolute URL path every version mounts under. |
| `APIVER_BASE_VERSION` | The name `apiver init` adopts the existing API as. |
| `APIVER_VERSIONS` | Hand-maintained list of live version names. |
| `APIVER_ALIASES` | Hand-maintained list of declared alias names. |
| `APIVER_VERSION_SCHEME` | The project's version-naming Scheme — `sequential` (default), `semver`, or `date` — used to validate, format, and chronologically order version names ([ADR 0008](docs/adr/0008-version-schemes.md)). |
| `APIVER_MAX_LIVE_VERSIONS` | Warning-level system check threshold for live versions (default **3**) — a maintenance-burden signal, not a hard limit; pair with `manage.py check --fail-level WARNING` in CI if you want it hard. |
| `APIVER_MANIFEST_PATH` | Where `apiver.toml` is read/written, if not the project root. |
| `APIVER_OUT_OF_BAND_ALIAS` | Alias namespace `apiver.reverse` falls back to for code with no request in reach (a Celery task, a management command). |
| `APIVER_PATCH_HYPERLINKED_FIELDS` | Set to `False` to opt out of apiver's version-aware `HyperlinkedRelatedField.get_url` patch. |

## Requirements

- Python 3.12–3.14
- Django ~5.2
- Django REST Framework ~3.18
- drf-spectacular ~0.30

## Installation

apiver isn't on PyPI yet — install it straight from GitHub until it is:

```console
$ uv add git+https://github.com/edraobdu/apiver.git
```

or with `pip`:

```console
$ pip install git+https://github.com/edraobdu/apiver.git
```

## Roadmap

**0.2 — `apiver diff` and `apiver check`.** Schema-diff-based breaking-change detection between two
versions, built on the same manifest `apiver versions` already reads. It will catch every "Yes"-marked
row in the [change-shape table](#whats-supported-today) above and, just as importantly, will document
— not silently paper over — the rows already known to be schema-blind (`SerializerMethodField` output,
permissions, pagination, filtering, default ordering, throttling, error shape).

**0.3 — `apiver init --move`.** Today, adopting apiver never relocates a file, on purpose — imports
invisible to the URLconf (settings strings, Celery task paths, admin registrations) would otherwise
silently break. `--move` will physically relocate and rewrite those imports for a project that wants
its scattered pre-existing code reorganized into apiver's layout, once generate-only adoption has
proven the wiring correct in the field.

**Near-term, alongside those:** multiple `--prefix` values for `apiver init` against projects whose
routes are scattered across several unrelated roots.

**1.0 — `apiver squash`.** Long delta chains are the natural worry with a deltas-forward design — by
`v12`, is the inheritance chain still maintainable? `squash` is the intended answer: flattening an
authored version's inheritance chain into standalone source via an LibCST-based codemod, so earlier
versions can be safely deleted. This is genuinely novel codemod work, so it's named here as a real
roadmap direction with an honest caveat, not a promise: it generates output plus a per-registration
clean/needs-review report and stops short of auto-promoting anything — you review and `git mv` it in
yourself. **Today's workaround** is declaring a fresh base version and archiving the old chain, which
needs no new tooling at all. The `APIVER_MAX_LIVE_VERSIONS` warning already ships in 0.1 specifically so
the "doesn't this get unwieldy" question has a real, live mechanism behind it before `squash` exists to
answer it structurally.

**Post-1.0, and only once a real need justifies it — FastAPI, Quart and Litestar adapters.** apiver's
public namespace is `apiver.drf`, not flat `apiver`, precisely so this stays possible without a
breaking rename later. There is deliberately no `apiver.core` abstraction layer built ahead of a second
framework actually needing one — building that layer speculatively, before a real adapter has stressed
it, is exactly the kind of premature flexibility this project's [philosophy](#philosophy) argues
against.

**Also open, not yet scheduled:** whether `Version` should support version-wide configuration
(`permission_classes`, authentication) that forwards to every route without an explicit `override()`
per endpoint — flagged as probably rare, and today's documented workaround is overriding each affected
endpoint explicitly.

## Status and stability

apiver is pre-1.0 and not yet on PyPI. The mechanism, verbs, and CLI documented above exist and are
covered by tests running against both the library's own suite and a real reference DRF project — this
isn't a design document describing something aspirational. What isn't settled yet is everything listed
under [Roadmap](#roadmap): expect the public API to keep moving until a tagged `0.1` release, and pin
an exact commit if you adopt apiver before then.

## Learn more

- [**docs/tutorial.md**](docs/tutorial.md) — the full adoption walkthrough, run for real against a
  working DRF project, commands and output included verbatim.
- [**docs/adr/**](docs/adr/) — the architectural decision records behind every non-obvious choice above:
  route identity, the public API surface, layout and the manifest, squash feasibility, intra-version
  hyperlinking, field removal, the Aggregation Root, and version schemes.
- [**CONTEXT.md**](CONTEXT.md) — the project's glossary: precise definitions for every capitalized term
  used throughout this README (`Version`, `Delta`, `Registration`, `Frozen`, `Live`, `Alias`, and more).
- [**CONTRIBUTING.md**](CONTRIBUTING.md) — development setup, tests, and lint.
