# What If...?

The objections a real adoption decision actually raises — answered plainly, including where the honest
answer is "not yet" or "that's a real boundary."

## What if my project already has years of tangled, inconsistent versioning?

Nothing about apiver assumes a clean starting point. `apiver init` adopts your project's current, live
routes as the **Base Version** exactly where they already are — one hand-rolled version or a dozen
(`v1` through `v30`, no consistent pattern), a single scheme or three abandoned attempts at one,
`if request.version` branches you'd rather not read again. apiver never inspects or cares how you got
there, because it was never tracking any of it: the Base Version `apiver init --base ...` creates is the
*first* version its name-validation ever sees.

That makes the naming scheme itself a genuinely free choice at the moment you adopt apiver — set
`APIVER_VERSION_SCHEME` to `semver`, `date`, or leave it `sequential` before running `apiver init`,
entirely independent of whatever ad-hoc numbering your project used before. Your years of `v1`...`v30`
never have to become "correct" retroactively; the Base Version apiver creates today simply *is* the
first name that scheme has ever validated. (Changing the scheme again later, once apiver is already
tracking versions under it, is a different and more constrained operation — see
[Version schemes](guides/version-schemes.md).)

## What if I use `semver`/`date` and the generated class names break PEP8?

They do, and on purpose. Python identifiers can't contain dots or hyphens, so a `semver` slug spells
`v1.2.3` as `v1_2_3`, and the version-suffix check (`register()`/`override()`'s `_check_suffix`) that
traces a class back to its Version needs that exact slug, uppercased, in the class name — `v1_2_3`
requires `V1_2_3` somewhere in the name, e.g. `UserViewSetV1_2_3`. There's no rule anywhere that a class
name must be strict PascalCase — that's convention, not syntax — but it's still worth knowing going in
if `V1_2_3` reads wrong to you. See [Version schemes](guides/version-schemes.md#class-names-under-semverdate)
for the full mechanics, including why versioning at patch granularity is usually the wrong instinct
here — a `semver` project generally only needs a new `Version` (and a new suffixed class) at a breaking,
major bump, not on every release.

## What if I already have an `/api/` folder and routes I don't want to touch?

`APIVER_ROOT_DIR` — the package apiver's own generated files live under — defaults to `"apiversions"`,
deliberately not `"api"`, precisely so it never collides with a project's pre-existing API app.
`apiver init` discovers and imports your **existing** views and serializers from wherever they already
live; it writes new files, but it does not move, rename, or rewrite a single line of code you already
have. Your existing `reverse()` calls, tests, Celery task paths, and admin registrations keep working
untouched, because the modules they point at haven't moved. See
[Getting Started](getting-started.md) for the adoption walkthrough end to end.

## What if I need to add a brand-new route after adopting apiver — is `path()` gone for good?

Only inside the versioned surface. Anything that's part of your API — a new resource, a new action, a
changed field — gets `register()`ed or `override()`n on a `Version` from then on, because that's the one
place `apiver versions`/`apiver diff` and the generated OpenAPI docs can see it. Everything else in the
project keeps using `path()`/`include()` exactly as before: `admin/`, health checks, a third-party
webhook or OAuth callback URL that needs a stable path no version prefix should ever touch. `apiver
init`/`apiver mount` only ever write inside their own generated Aggregation Root
(`apiversions/urls.py` by default) — wiring that into your project's actual root `urls.py` with one
line, `path("", include("apiversions.urls"))`, is something you do by hand, once; apiver never writes
to that file itself. Nothing routes every URL in the project through apiver's verbs, only the ones you
actually want versioned.

## What if my project uses a nested router?

`register_nested()`/`override_nested()` — a nested resource is an ordinary Registration whose key embeds
its parent's lookup group, and these are the sugar for writing that key without hand-rolling the regex:

```python
from catalog.views import CategoryViewSet, CollectionViewSet, ProductViewSet, ReviewViewSet

v1.register("categories", CategoryViewSet, basename="categories")
# Two siblings under the same parent — neither retypes the other's regex:
v1.register_nested("products", ProductViewSet, parent="categories", lookup="<int:category_pk>")
v1.register_nested("collections", CollectionViewSet, parent="categories", lookup="<int:category_pk>")
# A third level, nested under one of those siblings:
v1.register_nested("reviews", ReviewViewSet, parent="products", lookup="<int:product_pk>")
```

`lookup=` takes Django's own `path()` converter syntax, translated internally to the regex fragment DRF's
router needs — no regex to get right by hand, and no new dependency (it reuses `django.urls`'s own
converter parsing). Each call still produces exactly one ordinary Registration, individually targetable
by `override_nested()`/`remove()` exactly like any other — `v2.override_nested("reviews",
ReviewViewSetV2, parent="products", lookup="<int:product_pk>")` touches only that one leaf, no ancestor
regex retyped, parent resource untouched (ADR 0001 item 3).

What's still refused is passing an actual router *instance or class* as a handler to `register()` —
nesting was never expressed that way, and `register()`/`override()` each bind exactly one ViewSet or
view per call (ADR 0001 item 5).

A custom router apiver doesn't otherwise recognize is a different question: it hard-fails at
registration time, with every offending route named at once, rather than being composed into something
subtly wrong. Register those routes directly with `register()`/`override()` — apiver works uniformly
across ViewSets, `APIView`s, function views, and plain Django views, and doesn't require a router at all
— as the documented path today.

One case is still a known gap: nesting expressed as a parent lookup embedded in an *ancestor* `include()`
segment (`path("orders/<int:pk>/", include(child_router.urls))`) rather than in the router's own prefix.
`apiver init` doesn't discover that shape; author it with `register()`/`register_nested()` going forward
instead.

## What if I'm already using Cadwyn?

Cadwyn is the one other DRF/FastAPI-adjacent versioning tool doing real version composition rather than
just setting `request.version` and stopping — and it's actively maintained with genuine production
adoption, not a museum piece. It's also solving a different problem with the inverse architecture:
FastAPI-only, latest-canonical, with backward-transform modules reconstructing older versions from the
newest one. apiver stays forward from a Base Version instead — each later version is an explicit delta
against its *parent*, not a transform away from the *latest*. Neither replaces the other; if you're on
FastAPI, Cadwyn's already built for your stack. If you're on Django REST Framework and want the
delta-from-parent model with loud, narrow verbs, that's what apiver is for.

## What if I'm already using DRF's built-in `URLPathVersioning`?

`URLPathVersioning` sets `request.version` on the request and stops there — no fallback, no
composition. Everything past that point is up to you: hand-written `if request.version == "v2":`
branches in views, serializers, querysets, one per divergence, with nothing tying them together or
telling you what `v3` actually serves without reading every branch. apiver composes a complete resolution
table instead — `override()` once, and the other 95% of the surface resolves through to the parent's
actual handlers without a single conditional.

## What if I just sprinkle in `if request.version == "v2":`— isn't that simpler?

At one branch, yes. It stops being simpler the moment there's a second one on a different view, and a
third on a queryset — now the answer to "what does v2 actually serve" is "read every file for every
branch," and nothing stops the next one from being written slightly differently than the last. apiver
forces that same decision to be made in exactly one place, in a form (`register()`/`override()`/
`remove()`) that's identical every time — so the tenth divergence looks exactly like the first, and
`apiver versions` can answer "what does v2 serve" without you reading anything.

## What if my version chain reaches v12 — doesn't inheritance get unmaintainable?

That's the natural worry with any deltas-forward design, and it's what
[`apiver squash`](guides/version-lifecycle.md#squashing-a-long-delta-chain) exists for: it rewrites a
version's `registry.py` into an explicit, complete list of everything it resolves from its whole
ancestor chain — mechanical, not clever, because a version's root can only ever hold `registry.py`
(no `class`/`def` of its own), so there's never implementation code at risk of being folded away with
it. `git diff` is a complete review surface for the change. From there,
[`apiver remove`](guides/version-lifecycle.md#archiving-a-squashed-away-version) archives the versions
squash absorbed. `APIVER_MAX_LIVE_VERSIONS` (default 3, warning-level) is the nudge that tells you it's
time to start.

## What if I need to remove a field a lot of clients still depend on?

Immediate hard removal is the documented fast path for low-stakes fields nobody's realistically
depending on — but the recommended default is **deprecate, then remove**: soften the field in `V(n)`
with `required=False` and drf-spectacular's native `deprecate_fields`, giving clients a signal a whole
version ahead of the actual break, then hard-remove it via `Meta.fields` surgery in `V(n+1)`. See
[What's Supported](supported.md) for the full change-shape catalogue.

## What if my published OpenAPI schema drifts from what's actually live, or a change doesn't show up in a diff?

`apiver.toml` is a committed snapshot of every version's resolution table, and `apiver manifest --check`
exits non-zero the moment it's stale — the same idiom as `makemigrations --check`. Composition itself
re-walks its own output and hard-fails on any mismatch against what it intended to produce, so a
silently-wrong resolution table can't reach a request in the first place. `apiver diff`/`apiver check`
compare two versions' composed schemas plus their shared registrations' ordinary class attributes
(permissions, pagination, filtering, throttling, ordering) — and always print the same disclaimer this
site does: a `SerializerMethodField`'s output and a custom error-response shape are real, supported
changes that a schema diff genuinely cannot see, by construction, not a gap apiver is hiding. See
[What's Supported](supported.md#the-routingschema-boundary) for the complete, honest boundary.

## What if I set a serializer field to `None` to remove it, like I always do in Django forms?

apiver raises. It's the idiom every Django-forms-trained developer reaches for, and DRF silently ignores
it — the field survives in both the response and the schema, which is exactly the kind of silent
survival apiver is built to refuse. apiver walks the MRO at `register()`/`override()` time and points you
at `Meta.fields` surgery instead. The asymmetric exception: `refund = None` on a ViewSet subclass *does*
correctly remove an inherited `@action` — DRF's own `get_extra_actions()` already handles that one
cleanly, so apiver doesn't need to guard it.

## What if I'm not on Django REST Framework at all — FastAPI, Flask?

Not today. apiver's public namespace is `apiver.drf`, not flat `apiver`, specifically so framework
adapters can exist later without a breaking rename — but there's no `apiver.core` abstraction layer
built ahead of a second framework actually needing one. FastAPI, Quart, and Litestar adapters are
explicitly post-1.0, and only once a real second-framework need justifies building that layer against
something that's actually stressed it, rather than guessed in advance.
