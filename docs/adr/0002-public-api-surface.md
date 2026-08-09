---
status: accepted
---

# The public API surface: mutable-until-frozen Versions, split register/override, aliases as reused mounts

This is the surface a developer actually writes against — the one thing genuinely hard to change once
published to PyPI (ADR 0001's route identity is the internal data structure it's built on).

## Decision

1. **Construction:** `Version("v1")`, then `v1.derive("v2")` — the parent is set by the verb, not a
   constructor kwarg, so lineage order can't be passed out of sequence.

2. **Mutability is explicit, not automatic.** A `Version` stays mutable — `register()`/`override()`/
   `remove()` all work — until `v1.freeze()` is called. `derive()` does **not** require the parent to be
   frozen, and may be called any number of times off the same still-mutable parent. Composition is live:
   a derived Version's resolution table walks its parent at composition time, so registrations added to a
   mutable parent are visible to every existing child immediately, until that parent freezes.

   This makes branching (multiple children off one parent) fall out for free rather than being a feature
   to build — it's what you get by *not* restricting `derive()` to one call per parent. It's what a
   beta/experimental Version is: an ordinary `Version`, mounted under an experimental `Alias`, derived from
   a still-mutable base while real development continues on that same base in parallel. If it fails, it's
   dropped. If it succeeds, the real next Version is still derived independently from the frozen parent and
   the change is reapplied — a beta is never folded into permanent lineage, win or lose, so a temporary
   experiment's name never has to live forever in the inheritance chain, and squash (1.0) only ever has to
   flatten the one promoted line.

3. **`register()` and `override()` are separate verbs**, not one. `register()` raises if the key already
   exists anywhere up the parent chain; `override()` raises if it doesn't. Both apply identically to
   ViewSets (keyed by router prefix) and to APIViews/function views/plain Django views (keyed by literal
   path, requiring an explicit `name=` since there's no router to derive one). Kind is inferred by
   duck-typing on `.cls` (present on every DRF callable per ticket 02's research) — one verb pair regardless
   of what's being registered.

4. **`remove(key)`** uses the same key space, raising if the key isn't present in the resolved parent chain.

5. **Deprecation lives on the `Version` object** — `v1.deprecate(sunset=...)` — never on the manifest or in
   settings. The manifest is a generated snapshot for tooling that shouldn't need to import Django; code is
   authoritative.

6. **Package namespace is `apiver.drf`**, not flat `apiver`, from 0.1 on. The standing decision against an
   `apiver.core` abstraction layer is about not building shared indirection before a second adapter exists —
   it says nothing about where the DRF-specific modules live. A namespace segment costs nothing now; renaming
   the import path after publishing is the expensive mistake.

7. **Mounting is one line, identical in shape to plain DRF:** `path("api/v2/", include(v2.urls))`. `v2.urls`
   returns Django's `(patterns, app_name)` tuple internally, so ADR 0001's instance-namespacing happens
   without the developer ever typing a namespace by hand.

8. **Aliases are declared independently of `Version`** — `apiver.Alias("stable", target=v2)` — since an
   alias points *at* a Version without being owned by it, and is re-pointed by editing `target=`. An alias
   is mounted by reusing the target's exact callback objects at a second prefix
   (`path("api/stable/", include(stable.urls))`), never a fresh registration, and its schema route reuses
   the *same* `SpectacularAPIView` instance rather than generating a second document or proxying to one.
   The alias mount gets **its own Django instance namespace** — `include((v2_patterns, "v2"),
   namespace="stable")` — so `reverse("stable:payments-detail")` resolves to `/api/stable/...` and
   `reverse("v2:payments-detail")` independently resolves to `/api/v2/...`, even though both name the
   identical view. Without this, nothing apiver-aware (a `HyperlinkedIdentityField`, a `Location` header)
   could ever produce an alias-rooted link — the alias would only be reachable by a client hard-typing the
   URL, never by name.

## Considered options

- **Auto-freeze on first `derive()` call.** Rejected after walkthrough of the beta-testing scenario: it
  would make "start an experiment" and "stop being able to keep developing the thing it came from" the same
  action, which is wrong — those are independent decisions a developer needs to make separately.
- **A single `register()` verb** covering both new and replacing registrations. Rejected: it would silently
  turn a typo'd key into the wrong operation (a "new" registration that was actually an accidental override,
  or vice versa) instead of failing loudly, which is inconsistent with the self-verifying-composition
  precedent ADR 0001 already set.
- **A `BetaVersion` or similar special-purpose subtype.** Rejected — it's exactly the parallel object model
  the anti-goals list rules out. A beta is an ordinary `Version`; nothing about it needs new machinery.
- **Alias schema served via redirect/proxy to the target's document.** Superseded by empirical testing
  (below): reusing the same `SpectacularAPIView` instance at a second path is simpler and equally safe.
- **Manifest as the deprecation source of truth.** Rejected: it would mean two places can disagree about a
  Version's lifecycle, and the manifest is meant to be a derived artifact, not something hand-authored or
  authoritative.

## Consequences

**Empirically verified, not assumed:** the alias-duplication hazard ADR 0001 flagged (drf-spectacular's
dedup keys on `(path, method)`, not the callback) only manifests when schema generation walks the *entire*
urlconf. Scoping each version's `SpectacularAPIView` via `patterns=` to that version's own mounted patterns
prevents an alias's reused mount from leaking in or colliding, confirmed against Django 6.1 / DRF 3.18 /
drf-spectacular 0.30 in an ephemeral environment. This sharpens ticket 03's finding: `SCHEMA_PATH_PREFIX`
only affects operationId naming, not which endpoints are included — `patterns=` is the actual inclusion
mechanism, and every per-version schema view apiver generates must be constructed with it.

**This is the surface locked before 0.1 ships.** Everything downstream — the enforced layout (ticket 08),
the manifest format (ticket 08), squash (ticket 09) — now has a fixed vocabulary of verbs to build against.
