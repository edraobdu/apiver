---
status: accepted
---

# Links resolve through the Version serving the request, stamped at mount time

[ADR 0001](0001-route-identity.md) left one question explicitly open: authored Versions are
namespaced while the Base Version keeps bare URL names, so a view **inherited** from V1 into V2
will `reverse()` into V1 unless something makes it version-aware. Every hyperlinked field,
`Location` header and redirect target in inherited code points at the wrong version by default —
silently, with every route still resolving and every routing test still passing. This is the
class of quiet wrongness the rest of apiver's design exists to prevent, so it is settled before
0.1 ships rather than deferred.

Resolved against a working prototype (79 tests,
built on `reference/`). Findings below are measured, not reasoned.

## Decision

### Where the Version comes from

1. **The serving Version is stamped onto the request by a mount-time wrapper**, closing directly
   over the `Version` object — the same seam [ticket 12](../../.scratch/apiver-mvp/issues/12-gating-semantics.md)
   already chose for deprecation and sunset headers. Version-aware linking therefore adds no new
   machinery; it rides on a wrapper 0.1 was already going to build.

2. **The wrapper also sets a `ContextVar`**, not a threadlocal, so code with no request in reach —
   a bare `reverse()`, a model's `get_absolute_url()` — can still find the serving Version, and so
   the mechanism stays correct under async. Set and reset around each call, verified non-leaking
   across 80 interleaved threaded requests.

3. **Stamping at `register()`/`override()` time is rejected, not deferred.** A Registration made in
   V1 is inherited by V2 *as the same Python object*; `register()` runs once and there is no second
   call for V2 to hook. Any version state on the class or in a module global has one slot for N
   versions. Measured: a viewset stamped by V1 reports `v1` when served under `/api/v2/` and under
   `/api/stable/`, while the mount-time stamp reports `v2` correctly for both. Moving the write to
   dispatch time does not rescue it — it converts a wrong value into a race, since that one class
   object serves every version concurrently.

4. **Namespace resolution reads three sources, in order:** `resolver_match.namespace` (the
   *instance* namespace Django actually matched), then the stamped Version, then the out-of-band
   Alias from item 11. The first is what makes Aliases behave; the second is the only source that
   can also answer *which `Version` object* is serving, which `resolver_match` cannot do at all for
   the unnamespaced Base Version. They are not redundant — they answer different questions.

### Hyperlink fields: apiver's problem, not the developer's

5. **apiver patches `HyperlinkedRelatedField.get_url` during app loading.** The library does this;
   the developer never sees it, imports nothing and configures nothing. `get_url` is defined once,
   on `HyperlinkedRelatedField` ([relations.py:321](https://github.com/encode/django-rest-framework/blob/3.18.0/rest_framework/relations.py#L321)),
   and `HyperlinkedIdentityField` merely subclasses it — so a single patched method covers explicit
   fields, `HyperlinkedModelSerializer`'s auto-generated `url`, related/FK fields and nested
   serializers at once. No serializer walking, no class substitution.

6. **The patch is version-neutral, and therefore safe on a shared class.** It rewrites the view
   name from whatever Version is serving *this request* and stores no version anywhere. With no
   Version serving it is a no-op, verified against the reference project's own non-apiver URLconf.

7. **It has no import-order dependence, because `get_url` is late-bound.** `self.get_url(...)`
   resolves through the class at call time, so a field object built long before the patch still
   routes into it — measured on the same field instance before and after patching, and on a
   developer's own subclass defined beforehand. This is the property that makes a class-attribute
   interception point viable where a module-level one is not.

8. **A developer who overrides `get_url` themselves is not covered, and that is correct** — they
   have taken control of link generation explicitly.

### Bare `reverse()`: the developer's problem, stated plainly

9. **apiver ships `apiver.reverse` and patches neither `rest_framework.reverse.reverse` nor
   `django.urls.reverse`.** Adopting projects are told to replace every `reverse` import with
   `apiver.reverse` — a mechanical find-and-replace with no per-call judgement required.

10. **`apiver.reverse` is a genuine drop-in for both Django's and DRF's**, verified: returns a
    relative path with no request (identical to `django.urls.reverse` when no Version is serving),
    an absolute URI when given a request (as DRF's does), passes through Django-only keywords such
    as `query` and `fragment`, and **falls back to the bare name when the namespaced one does not
    resolve**. That fallback is load-bearing: without it, a project that replaced *every* `reverse`
    call would raise `NoReverseMatch` on the admin, a login page or a health check the moment a
    versioned request was being served. It does not downgrade versioned routes to the Base Version,
    and a genuinely unknown name still raises.

### Out-of-band code

11. **A new setting names the Alias that out-of-band code links against** (`stable` by
    convention), consulted only when there is no request and no ContextVar — a Celery task, a
    management command, a cron job. Falling back to the Base Version, as the mechanism did before
    this ADR, points such code at the **oldest** API: the first to be deprecated and the first to
    start answering 410.

12. **Linking out-of-band code at an Alias is documented as the recommended practice**, because an
    Alias moves as versions are promoted and the calling code never needs editing. Measured by
    promoting `stable` from V2 to V3: the identical call produced the identical URL string, served
    by a different implementation, with no caller changed.

13. **With one documented exception: links that get persisted.** A URL written into an email, a
    webhook registration or a database row is a stored artifact, and an Alias moving under it
    changes what it returns with no deploy on the holder's side. Right for a navigational link,
    wrong for a contract. Those pin a concrete version, which stays available via
    `apiver.reverse("v2:...")`.

### Aliases

14. **A request that arrived through an Alias keeps producing Alias-rooted links.** A client that
    deliberately pinned a movable name is not silently migrated onto a concrete version. The
    Version *identity* visible to application code remains the concrete target, so version-conditional
    logic still sees `v2` while the links say `/api/stable/`.

## Considered options

- **Stamping the view at `register()`/`override()` time** — the shape this was originally proposed
  in. Rejected on evidence (item 3), not on taste.
- **Setting the version on the view class at dispatch time.** Rejected: one class object serves
  every version concurrently, so this is a race by construction.
- **Patching `rest_framework.reverse.reverse`.** Rejected. `from x import y` binds early, so it
  reaches only modules imported *after* the patch. Django's loading order happens to favour it —
  `AppConfig.ready()` runs during `django.setup()`, the ROOT_URLCONF later — and an end-to-end
  simulation of that ordering did fix both fields. But it is a property of import timing, not a
  guarantee, and **when it misses it emits a wrong URL with no error**. A silent order-dependent
  failure is a worse trade than asking developers to change an import.
- **Patching `django.urls.reverse`.** Rejected as impossible, not merely unwise. DRF binds it at
  import (`from django.urls import reverse as django_reverse`,
  [reverse.py:5](https://github.com/encode/django-rest-framework/blob/3.18.0/rest_framework/reverse.py#L5)) —
  replacing `django.urls.reverse` with a sentinel and calling DRF's reverse never invokes the
  sentinel. Fifteen modules inside Django itself already hold direct references. The signature
  additionally carries no `request` and no `self`, and the function is shared with the admin, auth
  and every third-party app.
- **Substituting field classes during composition** (walking each serializer's declared fields and
  swapping them). Rejected as strictly more complex than item 5 while covering less — it would miss
  fields built dynamically and fields generated by `HyperlinkedModelSerializer`, both of which the
  `get_url` patch covers for free.
- **Reading `resolver_match.namespace` alone, with no stamp.** Rejected: it cannot identify the
  Base Version, which ADR 0001 leaves unnamespaced, and it cannot answer which `Version` object is
  serving — which gating and version-conditional application logic both need.
- **A threadlocal instead of a ContextVar.** Rejected: wrong under async, and apiver has no reason
  to ship a primitive that breaks the moment a project adopts ASGI.
- **Resolving Alias requests to the concrete version's URLs.** Rejected (item 14) — it would leak
  the concrete version to a client that deliberately asked for the movable name.
- **Leaving hyperlinks opt-in**, with developers swapping in an apiver field class. Rejected once
  item 5 proved the zero-effort path is both simpler and broader; an opt-in field would mean every
  inherited serializer needs editing, contradicting the promise that adoption changes no existing
  code.

## Consequences

**Adoption is free for hyperlinks and mechanical for `reverse()`.** This is the first place apiver's
adoption story splits: inherited serializers keep working untouched, while `reverse` imports need a
find-and-replace. The "Adopting apiver in an existing project" chapter owes both halves plainly,
including the `get_url`-override gap from item 8.

**apiver now monkeypatches a third-party class — its first.** That deserves a documented escape
hatch (a setting to disable the patch) and a standing obligation: the patch must stay inert on
projects that never adopted apiver, asserted in the test suite rather than assumed.

**The support matrix gains a specific obligation.** [#21](https://github.com/edraobdu/apiver/issues/21)
must assert that `HyperlinkedRelatedField.get_url` exists with the expected signature across the
pinned DRF range, alongside the existing `.cls`/`.initkwargs`/`.actions` assertions. This ADR's
zero-effort promise rests entirely on that one method staying where it is.

**Build it with gating, not after it.** The mount-time wrapper, the request stamp and the ContextVar
are one seam serving two features. [#13](https://github.com/edraobdu/apiver/issues/13) and this work
should land together rather than one retrofitting the other.

**`apiver.reverse` joins the public surface** fixed by [ADR 0002](0002-public-api-surface.md), and a
new setting joins `APIVER_MAX_LIVE_VERSIONS` from [ADR 0004](0004-squash-feasibility.md).

**The reference project owes a demonstration.** [#22](https://github.com/edraobdu/apiver/issues/22)
should show an inherited hyperlinked serializer producing correctly-versioned links under two
versions and an alias — it is the clearest single proof that inheritance composes behaviour and not
just routes.

**One refinement left deliberately unbuilt.** Item 10's fallback is try-namespaced-then-bare. Consulting
the Version's resolution table up front would be more precise — it would distinguish "this name is not
versioned" from "this name is versioned but you passed the wrong kwargs", which the current form
conflates into one retry. Cheap to switch once the resolution table is real; not worth pre-building.
