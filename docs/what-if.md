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

## What if I already have an `/api/` folder and routes I don't want to touch?

`APIVER_ROOT_DIR` — the package apiver's own generated files live under — defaults to `"apiversions"`,
deliberately not `"api"`, precisely so it never collides with a project's pre-existing API app.
`apiver init` discovers and imports your **existing** views and serializers from wherever they already
live; it writes new files, but it does not move, rename, or rewrite a single line of code you already
have. Your existing `reverse()` calls, tests, Celery task paths, and admin registrations keep working
untouched, because the modules they point at haven't moved. See
[Getting Started](getting-started.md) for the adoption walkthrough end to end.

## What if my project uses a custom or nested router?

Refused loudly, not silently mishandled. 0.1 composes against `SimpleRouter`/`DefaultRouter` semantics
only — a nested router or a custom one apiver doesn't recognize is hard-failed at registration time,
with every offending route named at once, rather than composed into something subtly wrong. Register
those routes directly with `register()`/`override()` (apiver works uniformly across ViewSets, `APIView`s,
function views, and plain Django views — it doesn't require a router at all) as the documented path
today.

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
