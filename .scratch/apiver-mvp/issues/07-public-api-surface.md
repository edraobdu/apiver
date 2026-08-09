# 07 — Public API surface and vocabulary

Type: grilling
Status: open
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
