# apiver

**Define API versions as deltas, not duplicates.**

[![CI](https://github.com/edraobdu/apiver/actions/workflows/ci.yml/badge.svg)](https://github.com/edraobdu/apiver/actions/workflows/ci.yml)

apiver is a Django REST Framework library for composing complete API versions from deltas. A **base
version** stays exactly where your existing code already lives; every later **authored version**
declares only what changed against its parent. Everything untouched resolves back through the chain to
the same handler objects the parent already uses — not copies of them — so every version presents a
complete, working API surface without duplicating the 95% of it that didn't change.

> **Status:** pre-1.0 (`0.1.0.dev0`). Everything documented below exists and is covered by tests, but
> nothing has shipped to PyPI yet and the public API can still move before a real `0.1` tag lands. See
> [Roadmap](#roadmap) for what's next, and [Status and stability](#status-and-stability) for what that
> means for you today.

## Table of contents

- [The problem](#the-problem)
- [Philosophy](#philosophy)
- [What you get](#what-you-get)
- [Quickstart: changing a field's type](#quickstart-changing-a-fields-type)
- [Adopting apiver](#adopting-apiver)
  - [Into an existing project](#into-an-existing-project-the-common-case)
  - [Into a new project](#into-a-new-project)
- [What's supported today](#whats-supported-today)
- [The routing/schema boundary](#the-routingschema-boundary)
- [Lifecycle: deprecation and sunset](#lifecycle-deprecation-and-sunset)
- [Version-aware links: apiver.drf.reverse](#version-aware-links-apiverdrfreverse)
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
- **Reach for a library.** Several DRF versioning packages have flatlined over the years, and none of
  the maintained ones do real version composition — they set `request.version` and stop there, leaving
  composition as an exercise for the developer.

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

**apiver enforces where routing is declared, never where the rest of your code lives.** The only file
any version — the base you adopted or a version you author later — is ever required to have is
`registry.py`, the one place its `register()`/`override()`/`remove()` calls happen. Your serializers,
views, and everything else stay wherever your project already organizes them; apiver has no opinion on
your file layout beyond that one file, the same way it has no opinion on your data layer or business
logic — how a field actually changes type in the database, what a request is allowed to do, how a
queryset gets built. apiver's job stops at the HTTP-facing shape of what crosses the wire, once per
version. That boundary is permanent, not a placeholder for tooling that doesn't exist yet: apiver will
never move, rename, or rewrite a file it didn't generate. `apiver init` discovers and imports your
existing code from wherever it already lives — it does not, and will not, relocate it.

## What you get

- **A second complete API surface for the cost of one field.** Change one type, add one subclass, call
  `override()` once — `GET /api/v2/users/` still works even though V2 never mentions users. The other
  95% of the surface was never touched, because it never had to be.
- **Adoption that doesn't ask you to reorganize anything first.** `apiver init` reads your existing,
  already-working DRF project and writes a base version around it — it never moves, renames, or rewrites
  a line of code you already have. There's no big-bang migration to schedule; you keep shipping, and the
  first breaking change is the only time you touch apiver again.
- **Deltas that are ordinary, inspectable Python.** An override is a subclass. There's no DSL, no
  parallel object model, no migration-chain classes to learn — if you can read a Django class hierarchy,
  you can read a delta.
- **Correct per-version OpenAPI, automatically.** Each version serves its own schema document containing
  exactly its own routes — no leakage from siblings, no duplicated operations from alias mounts, no
  hand-maintained schema file to keep in sync.
- **Lifecycle clients can actually see.** `v1.deprecate(sunset=...)` emits `Deprecation` and `Sunset`
  headers on every response, and returns `410 Gone` once the sunset date passes — enforced on the wall
  clock, so no deploy has to land on the date.
- **Tooling that answers the questions a version rollout always raises.** `apiver versions` prints what's
  served where and what's inherited; `apiver.toml` is a committed snapshot CI can assert is current — the
  answer to "what does v3 actually serve" is a command away, not an archaeology project.
- **An honest boundary, not a hidden one.** Route composition works for anything routable. Schema
  reasoning works only for what drf-spectacular understands. [More below](#the-routingschema-boundary).

## Quickstart: changing a field's type

The fastest way to see the whole mechanism is to change one field's type on one endpoint in a
brand-new version. The mechanism itself is deliberately not tied to any generated file layout —
`register()`/`override()` work on whatever class you hand them, imported from wherever it lives. The
one thing apiver does fix is where the wiring happens: `registry.py`. (In a real project, `apiver mount
v2 --from v1` scaffolds that file for you — see [Adopting apiver](#adopting-apiver) below.)

Start with an ordinary DRF resource — nothing apiver-specific about it yet. `price_cents` is an
integer, the same way every other amount in the system is stored — cents, to avoid float rounding:

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

Now say V2 needs to stop making clients divide by 100 in their own code — `price_cents` (an int) becomes
`price` (a decimal string). This is the change-shape that comes up constantly in real API versioning:
not a new field, an existing one reshaped out from under the clients still calling V1. The override
classes are ordinary additions to your existing `products` module — apiver doesn't ask you to put them
anywhere new:

```python
# products/serializers.py — same file as ProductSerializer above, just grown by one class
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


# Classes registered on a non-base version must carry the version's suffix —
# drf-spectacular names schema components off the class name alone, and apiver
# enforces this at override() time so two same-named classes in different
# versions can never collide silently.
class ProductSerializerV2(ProductSerializer):
    price = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = [*(f for f in ProductSerializer.Meta.fields if f != "price_cents"), "price"]

    @extend_schema_field(str)
    def get_price(self, obj):
        return f"{obj.price_cents / 100:.2f}"
```

```python
# products/views.py — same file as ProductViewSet above, just grown by one class
class ProductViewSetV2(ProductViewSet):
    serializer_class = ProductSerializerV2
```

`derive()` and `override()` are the entire delta — `registry.py` only ever states what changed, never
defines it:

```python
# api/v2/registry.py
from api.v1.registry import v1
from products.views import ProductViewSetV2

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

That's the whole change. `GET /api/v2/products/` now returns `price: "19.99"`; `GET /api/v1/products/`
still returns `price_cents: 1999`, and never changed. If `products/` were one endpoint out of thirty,
the other twenty-nine would need zero lines touched — V2 never mentions them, and they'd still resolve,
unchanged, straight through to V1's exact `ProductViewSet` object. That's the whole pitch: one field
reshaped, one subclass, one `override()` call, and a second complete API surface exists next to the
first one.

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
[quickstart](#quickstart-changing-a-fields-type) above, for whatever actually changed.

This is deliberately the same walkthrough as the full tutorial, run for real against a working DRF
project, commands and output included verbatim — see [**docs/tutorial.md**](docs/tutorial.md) for the
whole thing, including the six change-shapes that are easy to get subtly wrong (field rename,
whole-field removal, flat-to-nested restructuring, `SerializerMethodField` output changes, URL prefix
moves, and `@action` removal).

### Into a new project

Nothing above assumes an existing API. `apiver init` scaffolds a route-less base version when it finds
none under the given prefix, and you register your first resources directly on `v1` — there's no delta
to write yet, because a version's very first release has nothing to be a delta *against*. The moment
you need to break something, `apiver mount v2 --from v1` and the same `override()`/`register()`/
`remove()` verbs apply exactly as above.

## What's supported today

Route composition handles anything routable — ViewSets, `APIView`s, function views, plain Django views
— uniformly. Below is the full change-shape catalogue, including every awkward or schema-invisible case,
not just the easy ones:

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

## Version-aware links: apiver.drf.reverse

Every version gets its own Django instance namespace, so an ordinary `reverse("products-detail")`
called from inside a V2 view can't be trusted to resolve back into V2's own URLs — nothing about a bare
`reverse()` call knows which version is serving the request. `apiver.drf.reverse` is a drop-in
replacement for both `django.urls.reverse` and DRF's `rest_framework.reverse.reverse` that resolves
against the version actually serving the current request first:

```python
from apiver.drf import reverse

reverse("products-detail", request=request, kwargs={"pk": product.pk})
```

It isn't a monkeypatch — DRF's own `reverse` is bound at import time in fifteen-plus places inside
Django itself, so nothing short of an ordering guarantee could make patching it reliable. `apiver.drf.reverse`
is a mechanical find-and-replace instead: swap the import, keep every other argument (`args`, `kwargs`,
`format`, and Django-only keywords like `query`/`fragment`) exactly as it was.

Namespace resolution checks, in order: the namespace Django actually matched on the request (so a
request that arrived through an `Alias` keeps producing `Alias`-rooted links, not the concrete version
underneath it); the `Version` stamped onto the request at mount time; and, for code with no request in
reach at all (a Celery task, a management command), the `current_version` contextvar. If none of those
apply and `APIVER_OUT_OF_BAND_ALIAS` is set, that's the final fallback. A name that doesn't resolve
under the chosen namespace falls back to the bare name — load-bearing, since a project that replaced
every `reverse()` call with this one still needs its admin, login page, and health check to resolve
while a versioned request is being served — but a genuinely unknown name still raises `NoReverseMatch`.

`HyperlinkedRelatedField` and friends get the same version-aware resolution automatically, via a small
patch DRF's `get_url` applies on import; set `APIVER_PATCH_HYPERLINKED_FIELDS = False` to opt out. See
[ADR 0005](docs/adr/0005-intra-version-hyperlinking.md) for the full design.

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
| `APIVER_OUT_OF_BAND_ALIAS` | Alias namespace `apiver.drf.reverse` falls back to for code with no request in reach (a Celery task, a management command). |
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

**0.1 is the complete tool**, not a minimal one — everything below ships before the first tag, not
after it:

- **[`apiver diff` and `apiver check`](https://github.com/edraobdu/apiver/issues/76).**
  Schema-diff-based breaking-change detection between two versions, built on the same manifest `apiver
  versions` already reads. It catches every "Yes"-marked row in the
  [change-shape table](#whats-supported-today) above and, just as importantly, documents — not silently
  papers over — the rows already known to be schema-blind (`SerializerMethodField` output, permissions,
  pagination, filtering, default ordering, throttling, error shape).
- **[Multiple `--prefix` values for `apiver init`](https://github.com/edraobdu/apiver/issues/61).**
  Adopting a project whose routes are scattered across several unrelated roots (`api/`, `legacy/`,
  `internal-api/`) shouldn't need one `init` run per root plus hand-written `register()` calls for
  everything outside the biggest tree.
- **[A version-wide config layer](https://github.com/edraobdu/apiver/issues/57).** Still a decision
  ticket, not a build ticket: whether `Version` should support version-wide configuration
  (`permission_classes`, authentication) that forwards to every route without an explicit `override()`
  per endpoint. Today's workaround — overriding each affected endpoint explicitly — stays the documented
  path unless this lands with a real mechanism behind it.
- **[`apiver squash`](https://github.com/edraobdu/apiver/issues/77).** Long delta chains are the natural
  worry with a deltas-forward design — by `v12`, is the inheritance chain still maintainable? `squash` is
  the answer: flattening an authored version's inheritance chain into standalone source via an
  LibCST-based codemod, so earlier versions can be safely deleted. This is genuinely novel codemod work,
  named here with an honest caveat, not a promise: it generates output plus a per-registration
  clean/needs-review report and stops short of auto-promoting anything — you review and `git mv` it in
  yourself. **Today's workaround** is declaring a fresh base version and archiving the old chain, which
  needs no new tooling at all. The `APIVER_MAX_LIVE_VERSIONS` warning exists specifically so the
  "doesn't this get unwieldy" question has a real, live mechanism behind it before `squash` exists to
  answer it structurally.

**apiver will never relocate your existing files** — see [Philosophy](#philosophy). `apiver init`
discovers and imports code from wherever it already lives; that boundary doesn't move as the tool
matures, it's a permanent design decision, not a gap waiting on a `--move` flag.

**1.0 is a stability gate, not a new-feature milestone.** It means the public API — the verbs, the CLI,
the settings — has held under real adoption without a breaking change, not that new mechanism was
added to earn the tag.

**Post-1.0, and only once a real second-framework need justifies it — FastAPI, Quart and Litestar
adapters.** apiver's public namespace is `apiver.drf`, not flat `apiver`, precisely so this stays
possible without a breaking rename later. There is deliberately no `apiver.core` abstraction layer built
ahead of a second framework actually needing one — building that layer speculatively, before a real
adapter has stressed it, is exactly the kind of premature flexibility this project's
[philosophy](#philosophy) argues against.

## Status and stability

apiver is pre-1.0 and not yet on PyPI. The mechanism, verbs, and CLI documented above exist and are
covered by tests — this isn't a design document describing something aspirational. What isn't settled
yet is everything listed under [Roadmap](#roadmap): expect the public API to keep moving until a tagged
`0.1` release, and pin an exact commit if you adopt apiver before then.

## Learn more

- [**docs/tutorial.md**](docs/tutorial.md) — the full adoption walkthrough, run for real against a
  working DRF project, commands and output included verbatim.
- [**docs/adr/**](docs/adr/) — the architectural decision records behind every non-obvious choice above:
  route identity, the public API surface, layout and the manifest, squash feasibility, intra-version
  hyperlinking, field removal, the Aggregation Root, and version schemes.
- [**CONTEXT.md**](CONTEXT.md) — the project's glossary: precise definitions for every capitalized term
  used throughout this README (`Version`, `Delta`, `Registration`, `Frozen`, `Live`, `Alias`, and more).
- [**CONTRIBUTING.md**](CONTRIBUTING.md) — development setup, tests, and lint.
