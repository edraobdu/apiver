# 05 — Prove the mechanism (the weekend spike)

Type: prototype
Status: open
Blocked by: 01

## Question

Before any of the surrounding machinery is designed, prove the core mechanism survives contact with DRF **without ugly magic**. Throwaway code; the deliverable is knowledge, not a library.

Build a minimal Django project:

- **V1**: three resources — `users`, `payments`, `orders` — as router-registered ModelViewSets with serializers. Plus **one APIView** (e.g. `payments/summary/`), because [01](01-route-identity.md) made non-viewset routes first-class and the prototype must prove it.
- **V2**: overrides `payments` only (a `PaymentV2Serializer(PaymentV1Serializer)` changing one field's type), and **removes** one resource.

Then verify, by test:

1. `/api/v1/users/`, `/api/v1/payments/`, `/api/v1/orders/`, `/api/v1/payments/summary/` all work and use V1 implementations.
2. `/api/v2/users/`, `/api/v2/orders/`, `/api/v2/payments/summary/` all work and resolve to **V1** implementations.
3. `/api/v2/payments/` works and uses the **V2** serializer.
4. The removed resource 404s under V2 and still works under V1.
5. Registering V2 does **not** mutate V1 — the shared-mutable-registry trap from the Gemini thread. Assert V1 explicitly after V2 is built.
6. `reverse()` resolves correctly and unambiguously per version.
7. drf-spectacular generates a **complete** V2 schema (all four routes) with no duplicate operationId or component-name collisions.

The questions the spike must answer:

- Does the path-keyed resolution model from [01](01-route-identity.md) actually hold up when written out?
- How much of this is fighting DRF versus using it?
- **The acceptance test from ChatGPT's review:** would a 50-endpoint V1 → V2 migration where only 2 endpoints change feel almost trivial? Simulate it — generate 50 registrations and see whether the V2 file stays two lines.
- What broke that wasn't predicted?

Record findings in the Answer, including anything that argues the approach is wrong. A spike that kills the idea is a successful spike.

## Context

- Prototype lives at `.scratch/apiver-mvp/prototypes/05-spike/`. Throwaway — do not carry this code into the library.
- Settled: no `apiver.core` layer. Write it DRF-shaped.
- Settled: schema correctness is a 0.1 feature, so item 7 is not optional — see [03](03-spectacular-integration.md).
