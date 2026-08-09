# 07 — Public API surface and vocabulary

Type: grilling
Status: resolved
Assignee: claude
Blocked by: 01, 04

## Question

The part that is genuinely hard to change after publishing to PyPI. Everything else can be refactored; this can't.

Decide the complete public surface of 0.1:

1. **The version object.** `Version("v1")` + `v1.derive("v2")`? Or `Version("v2", parent=v1)`? Or a class-based declaration? Immutability: a `Version` is immutable once routes are registered, or mutable up to first use?

2. **Registration and override.** `v2.override("payments", PaymentV2ViewSet)` vs `v2.register(...)` vs a router-flavoured API. Must accommodate the path-keyed model from [01](01-route-identity.md) and non-viewset views. What does registering an APIView look like next to registering a viewset?

3. **Removal.** `v2.remove("payments")` — and whatever sub-route removal [01](01-route-identity.md) decided on.

4. **Aliases.** Versions are immutable, aliases are movable — `/api/v2/` always means V2, `/api/stable/` may change. How is an alias declared, and how is it mounted? Confirm the doc line: *aliases are convenience routes, not version identifiers.*

5. **Deprecation.** `v1.deprecate(sunset="2027-01-01")`? Where does status live — on the `Version` object, in the manifest ([08](08-layout-and-manifest.md)), in settings? Only one of those should be the source of truth.

6. **Mounting into `urls.py`.** What does the developer actually write in the root URLconf? This is the line every user sees first.

7. **Naming and vocabulary.** Keep it framework-neutral so a later FastAPI adapter presents the same surface, per the standing decision. Also settle whether the package exposes `apiver.drf` or a flat `apiver` namespace — it affects the import line in every example, and moving it later is a breaking change.

8. **What is deliberately NOT in the surface.** Per ChatGPT §16/§21: no `@version` decorators, no `if_version()`, no parallel object model, no `VersionManager`/`VersionMiddleware`/`VersionSchemaGenerator` sprawl. Write the anti-goals down so future tickets can be checked against them.

**The DX north star to test every option against:** the developer should still feel like they're using DRF. If the surface requires learning apiver's framework before writing an endpoint, it's wrong.

## Context

- Settled: DRF-only internals, framework-neutral public vocabulary. Keep the *names* portable, don't build the *layer*.
- Settled: `apiver`, `django-apiver`, `drf-apiver` are all free on PyPI (see [research/01-prior-art.md](../research/01-prior-art.md)). Name choice is [10](10-name-and-positioning.md).
- **Constraint from [05 — Prove the mechanism](05-prove-the-mechanism.md):** composition must build on `SimpleRouter`, not `DefaultRouter` — `DefaultRouter` emits an api-root view (plus a format-suffixed twin) even with zero registrations, breaking the 1:1 correspondence between a `Registration` and its resolved URL pattern that `diff`/`migrate`/squash need. If a per-version root listing is wanted, it has to be apiver's own construct, tracked in the resolution table, not DRF's.
- **Constraint from [06 — Field removal](06-field-removal.md):** the recommended field-deprecation workflow (`required=False` for requests, drf-spectacular's native `deprecate_fields` for responses) needs zero new public surface — no `deprecated()` field wrapper, no phase-out marker. Keep it that way; a marker is deferred to whenever `check` (0.2) exists to consume it, not introduced speculatively here.

## Answer

Recorded as [ADR 0002 — The public API surface](../../../docs/adr/0002-public-api-surface.md); glossary updated in [CONTEXT.md](../../../CONTEXT.md) (`Version` corrected from "immutable" to "mutable until Frozen"; `Frozen` and `Deprecation` added).

1. **Version:** `Version("v1")`, then `v1.derive("v2")` — parent set by the verb. Mutable until explicit `v1.freeze()`; `derive()` doesn't require a frozen parent and may be called any number of times off one still-mutable parent (branching is free, not a feature). Resolution is live — a child sees everything registered to its parent up to the moment the parent freezes. A beta/experimental Version is just an ordinary `Version` derived from a still-mutable base while real development continues on that same base in parallel; if it fails it's dropped, if it succeeds the real next Version is still derived independently from the frozen parent and the change is reapplied by hand — a beta is never folded into permanent lineage either way. No `BetaVersion` subtype.
2. **Registration:** two verbs, `register()` (raises if the key exists anywhere up the parent chain) and `override()` (raises if it doesn't) — loud failure over silent misclassification. Same verbs for viewsets (keyed by router prefix) and APIView/function-view/plain-View registrations (keyed by literal path, requires `name=`); kind inferred by duck-typing `.cls`.
3. **Removal:** `v2.remove(key)`, same key space, raises if the key isn't in the resolved parent chain.
4. **Aliases:** `apiver.Alias("stable", target=v2)`, declared independently of `Version`. Mounted by reusing the target's exact callback objects at a second prefix under **its own Django instance namespace** (`reverse("stable:payments-detail")` resolves independently of `reverse("v2:payments-detail")`) — never a fresh registration. Schema route reuses the same `SpectacularAPIView` instance rather than regenerating or proxying.
5. **Deprecation:** lives on the `Version` object (`v1.deprecate(sunset=...)`), never the manifest — code is authoritative, the manifest is a generated snapshot. Pre-answers ticket 08's "which wins" question.
6. **Mounting:** `path("api/v2/", include(v2.urls))` — identical shape to a plain DRF router; `v2.urls` applies ADR 0001's instance namespace automatically.
7. **Namespace:** `apiver.drf`, not flat `apiver`, from 0.1. Costs nothing now; renaming later is the expensive mistake the ticket itself flagged.
8. **Anti-goals confirmed:** no `@version` decorators, no `if_version()`, no parallel object model, no `VersionManager`/`VersionMiddleware`/`VersionSchemaGenerator` sprawl, no field-removal helper, no phase-out marker, no `BetaVersion`.

**Empirically verified** (Django 6.1 / DRF 3.18 / drf-spectacular 0.30, ephemeral `uv` env, no code committed): the alias-duplication hazard ADR 0001 flagged only manifests when schema generation walks the whole urlconf; scoping each version's `SpectacularAPIView` via `patterns=` to that version's own mounted patterns prevents leakage or collision either direction. Sharpens ticket 03: `SCHEMA_PATH_PREFIX` only affects operationId naming, not endpoint inclusion — `patterns=` is the actual inclusion mechanism.
