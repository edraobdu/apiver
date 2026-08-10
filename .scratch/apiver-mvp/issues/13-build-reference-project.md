# 13 — Build the reference project

Type: task
Status: resolved
Blocked by: —
Assignee: claude

## Question

**Correction (see resolution comment below):** this ticket was originally scoped to build V1 *and* V2 *and* the real apiver public API in one pass. That was wrong — it silently smuggled "build the library" into a ticket titled "build the reference project." Rescoped to match the title: this ticket builds only the pre-apiver V1 project — a plain, realistic, slightly messy DRF codebase, the kind that exists before anyone adopts apiver. No `apiver` code, no V2, no library.

1. Promote [05](05-prove-the-mechanism.md)'s spike's domain shape (`users`/`payments`/`orders`) — but organized the way a real pre-apiver project actually looks: separate Django apps at the project root (`users/`, `payments/`, `orders/`, ...), plain DRF (`DefaultRouter`, ordinary `ModelViewSet`/`APIView`/function views), no `api/v1/` structure yet since that only appears once `migrate` (future) writes `registry.py` into it.
2. Extend the resource set with enough field/behavior variety (a computed field, an extra `@action`, a resource meant to be removed later, a nested-vs-flat candidate, etc.) that the 22-row catalogue from [04](04-change-shape-catalogue.md) has real material to work against once V2 exists — planting the seeds, not building V2 itself.
3. The library (`apiver.drf`'s `Version`/`register`/`override`/`remove`/etc. per [07](07-public-api-surface.md) and [08](08-layout-and-manifest.md)) and V2 are **out of scope for this ticket**. They get built step by step, one capability at a time, each slice tested against this reference project — that breakdown is future fog/tickets, not this ticket.
4. The drf-spectacular correctness demo (row 4 of the original scope) waits until V2 exists; not applicable here.

## Context

- Shape and structure decided in [11 — Reference project: shape and structure](11-reference-project-shape.md).
- Full classification table: [04 — The change-shape catalogue](04-change-shape-catalogue.md).
- Spike proving the mechanism: [05 — Prove the mechanism](05-prove-the-mechanism.md), archived under `.scratch/apiver-mvp/prototypes/05-spike/`.
- Public API to build against: [07 — Public API surface](07-public-api-surface.md), [ADR 0002](../../docs/adr/0002-public-api-surface.md).
- Enforced layout to build under: [08 — Enforced layout and the version manifest](08-layout-and-manifest.md), [ADR 0003](../../docs/adr/0003-layout-and-manifest.md).
- Graduated from the map's "Not yet specified: 0.1 build slices" once [11](11-reference-project-shape.md) resolved.

## Answer

Built on branch `feat/13-reference-project`, under `reference/` — a standalone Django+DRF project with its own `pyproject.toml`/`uv.lock`, no dependency on the (nonexistent) `apiver` package.

**Shape:** four plain Django apps at the project root — `users/`, `payments/`, `orders/`, `legacy/` — each with its own `models.py`/`serializers.py`/`views.py`, wired together in `config/urls.py` via a plain `DefaultRouter`. This is deliberately *not* apiver-flavored: no `api/v1/` directory, no `registry.py`, no version-suffixed class names — that structure only appears once `migrate` (unbuilt, future) writes into it. A stray top-level `healthz.py` (function view, `@api_view`) and `payments/views.py::PaymentsSummaryView` (plain `APIView`) prove routes don't have to be router-registered ModelViewSets.

**Seeds planted for the future catalogue work** (each maps to a row in [04](04-change-shape-catalogue.md), to be exercised once V2 exists):
- `payments`: `display_amount` (`SerializerMethodField`, diff-blind — row 10), `card_last4`/`card_brand` flat fields (nesting-restructure candidate — row 9), `refund` extra `@action` (removal candidate — row 14b), `IsAuthenticatedOrReadOnly` (permission-change candidate — row 15), default `ordering = ["-created_at"]` (silent-break candidate — row 18).
- `legacy` app / `legacy-invoices`: a whole resource meant to not exist in V2 (row 12), the literal example from ticket 04.
- `orders`: plain, no frills — also a whole-resource-removal candidate, or left alone as a control.
- `users`: plain CRUD, a stable base for less eventful field-level rows (add/change/rename).

**Verified working**, not just written: `manage.py check` passes, migrations generated for all four apps, and 8 smoke tests (`reference/tests/test_smoke.py`) exercise every route via Django's real test client — CRUD, the `refund` action (behind auth), the sibling-route-ordering hazard (`/api/payments/summary/` not swallowed by the router's detail pattern), `legacy-invoices`, `healthz`, and `/api/schema/` generation.

**Explicitly out of scope, left for later, smaller tickets:** the `apiver.drf` library itself (`Version`/`register`/`override`/`remove`/`Alias`/gating/the enforced-layout check), V2, and the drf-spectacular correctness demo. Building those step by step — one library capability at a time, each slice tested against this reference project — stays fog on the map, not resolved here.
