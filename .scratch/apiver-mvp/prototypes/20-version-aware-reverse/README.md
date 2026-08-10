# Prototype: version-aware reversing (ticket [#20](https://github.com/edraobdu/apiver/issues/20))

**Frozen snapshot, not living code.** This directory (`spike/`, `tests/`) is the exact code
this investigation ran, archived here after `prototype/20-version-aware-reverse` was deleted
— the same convention [`05-spike`](../05-spike/) already established. It depended on
`reference/`'s `users`/`payments` apps as they existed at the time and is **not** wired to run
against the current `reference/` tree; treat it as a read reference for whoever builds this
capability for real, not a runnable test suite. **The decision itself is [ADR
0005](../../../../docs/adr/0005-intra-version-hyperlinking.md)** — that document is authoritative;
this one is supporting evidence.

**Verdict: the idea works, but not at the moment it was proposed.** Stamping the serving
Version onto the *request* at **mount time** solves intra-version hyperlinking completely,
including for views V2 never mentions. Stamping the view at **`register()` time** cannot
work, and the prototype demonstrates exactly why rather than arguing it.

Built against `reference/` on the now-deleted branch `prototype/20-version-aware-reverse`.
79 tests passed at the final commit (9 pre-existing smoke tests untouched, 70 new). Spike
code archived under [`spike/`](spike/), tests under [`tests/`](tests/).

## What was proposed

> Decorate the views right from `register()`/`override()`, passing the specific version
> they're acting on, so they can catch that version wherever they are — then decorate
> `reverse()` and so on.

The instinct — *the view should know which version is serving it, and everything else
follows* — is right, and it is what the prototype implements. Only the attachment point
moves.

## Why `register()` time cannot work

A registration made in V1 is inherited by V2 **as the same Python object**. `register()`
runs once, in V1, and there is no second call for V2 to hook — that absence is the whole
point of the deltas-forward design.

The prototype implements the proposal literally: `register_viewset()` sets
`viewset.stamped_at_register = self.name`. Then it serves the same viewset under three
mounts:

| Request | `stamped_at_register` | `stamped_on_request` |
|---|---|---|
| `GET /api/v1/payments/whoami/` | `v1` | `v1` |
| `GET /api/v2/payments/whoami/` | **`v1`** ← wrong | `v2` |
| `GET /api/stable/payments/whoami/` | **`v1`** ← wrong | `v2` |

Asserted directly rather than inferred: `v1.resolution_table()["payments"] is
v2.resolution_table()["payments"]`. One `Registration`, one handler class, three mounts.

This isn't a fixable detail of the proposal. Any version state living on the class or in a
module global has exactly one slot for N versions. Moving the write to dispatch time
doesn't rescue it either — it converts a wrong-value bug into a race, because that one
class object serves every version concurrently.

## What works instead

Wrap each version's callbacks at **mount time**, closing over the `Version`:

```python
def _stamp_version(callback, version):
    @wraps(callback)
    def wrapper(request, *args, **kwargs):
        request.apiver_version = version
        return callback(request, *args, **kwargs)
    return wrapper
```

`Version.urlpatterns()` applies it to every resolved callback. Because the wrapper is per
*mount* and not per *registration*, the same handler class gets a different wrapper under
each version — which is precisely the distinction `register()` can't express.

**This is the seam gating already needs.** Ticket 12 chose a mount-time wrapper closing
over the `Version` for `Deprecation`/`Sunset` headers, for the same reason (it works for
the unnamespaced Base Version, which `resolver_match` alone cannot identify). Version-aware
reversing rides along on machinery [#13](https://github.com/edraobdu/apiver/issues/13) is
already committed to building.

### Measured results

`PaymentV1Serializer` is declared **only** in V1. V2's registry never mentions `payments`.

```
GET /api/v1/payments/        url: http://testserver/api/v1/payments/1/       served_by: v1
GET /api/v2/payments/        url: http://testserver/api/v2/payments/1/       served_by: v2
GET /api/stable/payments/    url: http://testserver/api/stable/payments/1/   served_by: v2
```

The naive serializer alongside it — plain `HyperlinkedIdentityField` and plain
`reverse()`, i.e. what every DRF developer writes today — confirms the bug is real:

```
GET /api/v2/naive-payments/  url: http://testserver/api/v1/naive-payments/1/   ← wrong version
```

Generated links were followed and resolve (200), so this isn't string-shaped correctness.

## Two sources of truth, doing two different jobs

The prototype's `namespace_for(request)` reads `resolver_match.namespace` first and falls
back to the stamped Version. Both are load-bearing, for different questions:

- **`resolver_match.namespace` → which URL namespace should links use.** It reflects the
  *instance* namespace actually matched, which is what makes aliases behave: a client that
  came in through `/api/stable/` keeps getting `/api/stable/` links instead of having the
  concrete version name leak out. Empty for the Base Version, which is correct — bare names.
- **The request stamp → which `Version` object is serving.** `reverse()` doesn't need this,
  but everything else does: version-conditional serializer logic, gating, and any
  `SerializerMethodField` that wants to branch. `resolver_match` can't answer it at all for
  the Base Version, which is unnamespaced by ADR 0001.

So the stamp isn't redundant with Django's own machinery — it answers the question Django
can't. Worth deciding deliberately in the ADR rather than picking one.

## What it costs

**Nothing measurable in transparency.** `functools.wraps` copies `__dict__`, which is where
DRF puts `.cls`, `.initkwargs` and `.actions` — the attributes ADR 0001's route identity and
drf-spectacular both read. Asserted on every viewset-backed callback, and drf-spectacular
generates a full schema through the wrappers (`/api/v1/payments/{id}/` and
`/api/v2/payments/{id}/` both present).

**Thread-safe.** 120 interleaved requests across 16 threads alternating between `/api/v1/`
and `/api/v2/`; every response reported its own version. This is the property the
class-attribute alternative cannot have.

**Developer effort is real but opt-in.** As anticipated in the proposal, developers must use
`apiver`'s primitives instead of DRF's — `VersionedHyperlinkedIdentityField` rather than
`HyperlinkedIdentityField`, `apiver_reverse()` rather than `reverse()`. Per field, per call,
and only where a link is generated.

## Limitations found

1. **No request, no version.** `apiver_reverse("payments-detail", request=None)` silently
   returns the Base Version's URL. A Celery task, a management command, or a model's
   `get_absolute_url()` cannot be version-aware by this mechanism — there is no request to
   carry the stamp. This is a genuine hole and it fails *quietly*. **Partly closed in
   Round 2** by a ContextVar — it now works during a request; only genuinely out-of-band
   callers (Celery, management commands) still fall back.
2. **Except for hyperlink fields, which fail loudly** — better than predicted. DRF's own
   `to_representation` asserts `'request' in self.context`, so a hyperlink field raises with
   a clear message rather than emitting a wrong URL. The silent fallback in (1) can only
   bite bare `apiver_reverse()` calls.
3. **Alias-rooted links are a design choice, not a discovery.** The prototype makes
   `/api/stable/` links stay `/api/stable/`. The alternative — always resolving to the
   concrete version — is defensible too. Chosen because a client that deliberately pinned
   the movable name shouldn't be silently migrated onto a concrete one, but it needs an
   explicit decision.

## Round 2: can this be free for the developer?

The first round left version-awareness opt-in — developers swap `HyperlinkedIdentityField`
for apiver's field and `reverse()` for `apiver_reverse()`. Round 2 asks whether that swap
can be removed entirely. **Mostly yes.**

Everything below exercises `spike/plain/serializers.py`, which imports nothing from apiver,
declares no `url` field at all (it's a `HyperlinkedModelSerializer`), and is never modified.
The only variable is whether apiver's patch is installed.

```
              PLAIN DRF SERIALIZER, apiver patch NOT installed
GET /api/v1/plain-payments/    url: .../api/v1/plain-payments/1/
GET /api/v2/plain-payments/    url: .../api/v1/plain-payments/1/   ← wrong
GET /api/stable/plain-payments/ url: .../api/v1/plain-payments/1/  ← wrong

              SAME SERIALIZER, UNCHANGED, patch installed
GET /api/v1/plain-payments/    url: .../api/v1/plain-payments/1/
GET /api/v2/plain-payments/    url: .../api/v2/plain-payments/1/   ← fixed
GET /api/stable/plain-payments/ url: .../api/stable/plain-payments/1/ ← fixed
```

### One patch point covers every hyperlink shape

`get_url` is defined **once**, on `HyperlinkedRelatedField` (relations.py:321);
`HyperlinkedIdentityField` merely subclasses it. Patching that single method covers
explicit fields, `HyperlinkedModelSerializer`'s auto-generated `url`, related/FK fields,
and nested serializers — no serializer walking, no class substitution, no developer import.

The patch is **version-neutral**: it rewrites the view name from whatever version is
serving *this request*, and stores no version anywhere. That is what makes it safe on a
class shared by every version, and it's why it's inert on projects that never adopted
apiver (verified against the reference project's own non-apiver urlconf).

### The residue: bare `reverse()`

| What the developer writes | Free? | How |
|---|---|---|
| `HyperlinkedIdentityField` (explicit) | ✅ | `get_url` patch |
| `HyperlinkedModelSerializer` auto `url` | ✅ | same |
| `HyperlinkedRelatedField` (FK links) | ✅ | same |
| Nested hyperlinked serializers | ✅ | same |
| `from rest_framework.reverse import reverse` | ⚠️ | module rebind — **import-order dependent** |
| `reverse()` with no request (model method) | ⚠️ | ContextVar, during a request only |
| `from django.urls import reverse` | ❌ | no request, no `self`, shared with the admin |
| Celery task / management command | ❌ | no request cycle at all |

**The ContextVar closes the no-request hole.** The mount-time wrapper now also sets a
`ContextVar` (not a threadlocal — correct under async), so `reverse()` with no request
still resolves to the serving version. Verified reset after each request and non-leaking
across 80 interleaved threaded requests.

**The import-order gamble is real, and it fails silently.** `from x import y` binds early,
so patching `rest_framework.reverse.reverse` only reaches modules imported *afterwards*.
Both directions are tested explicitly:

- module imported **before** the patch → keeps the original `reverse`, links stay V1
- module imported **after** the patch → picks it up, links become V2

Django's ordering favours us: `AppConfig.ready()` runs during `django.setup()`, while the
ROOT_URLCONF (and therefore the developer's serializers) is imported later, on first
resolve. Simulated end-to-end, both `url` **and** `receipt_link` come out V2-rooted with no
change to the serializer. But it is a property of import timing, not a guarantee — and when
it breaks it produces a wrong URL with no error, which is precisely the silent-wrongness
class the rest of apiver's design goes out of its way to prevent.

### Recommendation

Split the two, because they carry very different risk:

- **Patch `get_url` by default.** It is a single method, version-neutral, inert without a
  version, and covers the overwhelming majority of link generation. This is what makes
  adoption genuinely free.
- **Do not patch `reverse()` by default.** The failure is silent and order-dependent. Ship
  `apiver.reverse()` as the explicit call, plus the ContextVar so it works without a
  request. Consider a system check that warns when the patch didn't take.
- **Document `django.urls.reverse` as out of reach.** There is nothing to intercept safely.

## Open questions for the ADR

- **Should the versioned field be the default?** apiver could substitute its own field class
  during composition so plain `HyperlinkedIdentityField` just works. Zero developer effort,
  but meaningful magic, and it would silently change behaviour in inherited code. Not
  prototyped.
- **Does `apiver_reverse` belong in the public surface**, or should it be a `Version` method?
  ADR 0002 fixed the vocabulary; this adds to it.
- **What about `reverse()` with no request** (limitation 1) — document as a known hole, or
  provide an explicit `version.reverse(...)` for out-of-band callers?
- **Naming.** `VersionedHyperlinkedIdentityField` is long, and `CONTEXT.md`'s glossary has no
  entry for any of this yet.

## Reproducing

The branch this ran on is gone. To rerun it, drop `spike/` back into a `reference/` tree
shaped like it was at the time (`users`/`payments` apps with the fields this code expects)
and point pytest at the copied `tests/`:

```bash
cp -r spike tests /path/to/a/reference/checkout/
cd /path/to/a/reference/checkout && .venv/bin/python -m pytest tests/ -q
```

Throwaway code. The composition core is adapted from the 05 spike and is not a design
proposal — only the stamping wrapper, `namespace_for()`, and the field are.
