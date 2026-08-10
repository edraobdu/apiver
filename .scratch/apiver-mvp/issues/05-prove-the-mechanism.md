# 05 — Prove the mechanism (the weekend spike)

Type: prototype
Status: resolved
Blocked by: 01
Assignee: claude

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

## Answer

**Verdict: the mechanism survives contact with DRF. No fatal flaw found.** All 17 tests pass (7 numbered verification items, the 50-endpoint acceptance test, plus 2 regression tests for hazards found along the way). Full code and test run archived under `.scratch/apiver-mvp/prototypes/05-spike/` — see the context pointer below.

**1–7 (verification items):** all confirmed as specified. V1 routes serve V1 implementations; V2 inherits `users` and `payments/summary/` unchanged (same class objects, not reimplementations — checked by identity, not just behavior); `/api/v2/payments/` uses `PaymentV2Serializer` (JSON renders as a decimal string, `"1500.00"`, vs. V1's plain int `1500` — a good visible signal the override actually took); the removed `orders` 404s under V2 and keeps working under V1; V1's registration table and live routes are provably unmutated after V2 is built (checked object identity, not just re-running the same assertions); `reverse("payments-detail", ...)` and `reverse("v2:payments-detail", ...)` resolve to different, correct URLs — the bare name never got hijacked by V2's later registration; V2's schema is complete (5 paths: `payments` list/detail, `payments/summary/`, `users` list/detail — `orders` absent) with no duplicate `operationId`s and no component collisions (`PaymentV2` present, `PaymentV1` absent from V2's document).

**Does the path-keyed resolution model (ADR 0001) hold up?** Yes, with zero surprises in the routing logic itself. Whole-registration override/removal, walking the parent chain and applying removals-then-overrides, was a ~15-line method (`Version.resolution_table()`) with no edge cases that needed special-casing.

**How much of this is fighting DRF vs. using it?** Overwhelmingly *using* it. The entire throwaway composition layer (`apiver_core.py`) is ~90 lines: a dataclass, a dict-merge for inheritance, and Django's own `include()` + instance-namespace machinery for the V1-bare-name / V2-namespaced-name split. No monkeypatching, no metaclasses, no private-API reach beyond what [02](02-urlconf-walk-feasibility.md) already catalogued as necessary.

**The 50-endpoint acceptance test:** passed as designed. `v2`'s registration code for the big-catalogue simulation is exactly two statements (one override, one removal); the other 48 resources are inherited *by object identity* (`table_v2[key] is table_v1[key]`) — genuinely zero-cost, not just visually short.

**What broke that wasn't predicted — two real findings:**

1. **`DefaultRouter` breaks the 1:1 correspondence between registrations and resolved URL patterns.** Even with zero registrations, `DefaultRouter().urls` emits 2 patterns (an api-root view plus its format-suffixed twin) that don't trace back to any `Registration`. Confirmed directly: `DefaultRouter()` with an empty registry → `['', '<drf_format_suffix:format>']`; `SimpleRouter()` → `[]`. Since `diff`/`migrate`/squash all need to reason about "which registration produced this path," an untraceable extra route is a real hazard, not cosmetic. **Fixed in the spike by switching to `SimpleRouter`.** This is a concrete decision the real library should inherit — flagged in [07](07-public-api-surface.md)'s context, since router class is part of what "registration and override" needs to settle. If a per-version browsable root listing is wanted later, it should be apiver's own construct (tracked in the resolution table), not DRF's.

2. **Route ordering is load-bearing, not stylistic.** DRF's default detail regex (`^payments/(?P<pk>[^/.]+)/$`) is generic enough to swallow `payments/summary/` as a detail lookup with `pk="summary"` if router-generated patterns are tried before explicit view patterns. The spike places non-router `view` registrations first in `urlpatterns()` for exactly this reason, and has a regression test (`test_summary_route_not_swallowed_by_detail_route`) pinning it down. Any real implementation needs this ordering documented as a constraint, not left as an accident of dict-iteration order.

**A third, smaller finding — not a bug, confirms an existing standing decision:** a plain `APIView` with no `serializer_class`/`GenericAPIView` base (`PaymentsSummaryView`) *is* routed and *does* appear in the schema (drf-spectacular logs "unable to guess serializer... Ignoring view for now" but still emits an operation), just with degraded content (`"responses": {"200": {"description": "No response body"}}` instead of the real `{total, count}` shape). This is direct empirical evidence for the map's standing decision — "route composition works for anything; schema reasoning works only for what drf-spectacular understands" — and feeds the still-open "APIView schema depth" fog item (revisit at 0.2).

**Capture:** spike code (`spike/`, `tests/`, `pytest.ini`, `README.md`) committed to the throwaway branch `prototype/05-mechanism-spike` at the time, later archived under `.scratch/apiver-mvp/prototypes/05-spike/` once the branch was deleted. The `.venv/` used to run it is gitignored and not part of that commit; recreate with `uv venv && uv pip install --python .venv/bin/python django djangorestframework drf-spectacular pytest pytest-django`.
