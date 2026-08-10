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

## Addendum — reference project substantially expanded (2026-08-10)

Requested directly (not a re-opening of this ticket's original scope): the four-app V1 above left roughly a third of [04](04-change-shape-catalogue.md)'s 22 rows with no concrete seed at all, and every resource shared one centralized `config/urls.py`, which never exercised anything but the flattest possible URLconf shape. Both gaps close here, still entirely within this ticket's original boundary — **V1 only, no V2, no library code.**

**Three new apps**, each real enough to carry its own kind of messiness rather than being a bag of fields bolted onto an existing app:

- `addresses` — the project's first relational field (`Address.user` → `UserProfile`, FK). Read/write serializer split (`AddressReadSerializer` nests the user; `AddressWriteSerializer` takes a bare FK id) — a genuine, common real-world pattern, not invented for the catalogue. A country-aware postal-code validator lives in its own `validators.py` and can only be expressed as object-level `validate()` logic (row 7 — trivial to write, invisible to a schema diff). `SearchFilter` (row 17, the `search=` half — `payments` already had the `ordering=` half).
- `notifications` — `NotificationCursorPagination` (`page_size=5`), deliberately distinct from the project's global `PageNumberPagination` default (row 16). `UserRateThrottle` attached to the viewset (row 20). A plain function-based `mark_all_read` view — a second non-viewset route type, and a second instance of the explicit-before-router ordering hazard. Its serializer is named `NotifSerializer`, not `NotificationSerializer` — deliberate naming drift, the kind every app in this project *except* this one has avoided so far.
- `webhooks` — a `secret` field with `write_only=True`: accepted on create, never returned by any read (row 22, concretely — the mirror image of an ordinary read-only field like `id`). A field-level `validate_target_url()` rejecting `http://` in favor of `https://` (row 7's second seed). A custom `WebhookDeliveryError(APIException)` raised from a `test_delivery` `@action`, returning `422` with a body shaped nothing like DRF's usual `{"detail": ...}` (row 19, concretely). Mounted at `api/integrations/webhooks/` — two segments deeper than every other resource, and the project's first plausible URL-prefix-rename candidate (row 13) that isn't also a delete+add.

**One addition to an existing app:** `orders/export/` (`OrdersExportView`, a plain `APIView`) with a hand-rolled `OrdersCSVRenderer(BaseRenderer)` — a non-JSON `renderer_classes` override (row 21), and a third instance of the explicit-before-router hazard.

**Every app now owns its own `urls.py`**, included from a `config/urls.py` that does nothing but recurse into them — `users`/`payments`/`legacy`/`webhooks` keep `DefaultRouter`, `orders`/`addresses`/`notifications` use `SimpleRouter`, matching how router choice actually drifts across a codebase built by more than one person over time rather than from a single shared scaffold. This wasn't for its own sake: apiver's `migrate` (ticket 02) has to walk the *resolved* URLconf tree regardless of how many `include()` layers produced it, and a project with one flat centralized router never exercised that. It does now — `webhooks` alone sits two `include()`s deep. As a direct consequence, the project now also reproduces [05](05-prove-the-mechanism.md)'s finding about `DefaultRouter` emitting an untraceable `api-root` pattern per registration point, four times over instead of once, since four apps each instantiate their own `DefaultRouter()`.

**Row coverage, updated.** Previously thin or unseeded: **7** (validation — addresses + webhooks, two seeds), **9** (nesting — now both directions: payments flattens, addresses nests), **13** (URL prefix — webhooks), **16** (pagination style — notifications), **17** (search, not just ordering — addresses), **19** (error shape — webhooks), **20** (throttling — notifications), **21** (renderer — orders), **22** (read-only/writable — webhooks, concretely rather than only by implication). Rows needing no dedicated seed (1, 2, 4, 5, 6, 11, 15) are unchanged from the original build and still don't need one — they're either trivially demonstrable on any existing field, or already covered.

**Verified working, not just written:** `manage.py check` passes; migrations generated for all three new apps; the full resolved URL tree was printed and inspected by hand; `drf-spectacular`'s schema generator runs clean across every app (the only warnings are the pre-existing, already-documented bare-`APIView` degradation, now joined by two more of the same kind — expected, not new); 25 pytest tests pass (`tests/test_smoke.py`'s original 9, unchanged, plus 16 new across `test_addresses.py`, `test_notifications.py`, `test_webhooks.py`, `test_orders_export.py`), stable across shuffled subsets and repeated runs. A `tests/conftest.py` autouse fixture now clears Django's cache between tests — needed once a throttle entered the picture, since throttle counters live in the cache and plain pytest functions get none of `TestCase`'s automatic per-test isolation for it.

**Still explicitly out of scope:** V2, the `apiver.drf` library, and the drf-spectacular correctness demo — unchanged from above.
