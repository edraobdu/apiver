# 13 — Build the reference project

Type: task
Status: open
Blocked by: —
Assignee: claude

## Question

Construct the permanent reference DRF project per [11](11-reference-project-shape.md)'s decisions:

1. Promote [05](05-prove-the-mechanism.md)'s spike (branch `prototype/05-mechanism-spike`) — carry forward its `users`/`payments`/`orders` resources, serializers, and routes. Discard its throwaway `apiver_core.py`; replace with the real public API ([07](07-public-api-surface.md)) under the enforced layout ([08](08-layout-and-manifest.md)).
2. Extend the resource set as needed so all 22 rows of [04](04-change-shape-catalogue.md)'s catalogue are represented somewhere in the project.
3. Explicitly demonstrate the documented idiom for all six awkward/undetectable rows: 5 (rename), 6 (field removal), 9 (nesting restructure), 10 (`SerializerMethodField` output), 13 (URL prefix change), 14b (`@action` removal).
4. Confirm the same project's V2 schema at `/api/v2/docs` serves as the drf-spectacular correctness demo ([03](03-spectacular-integration.md)) — complete, no duplicate `operationId`s, no component-name collisions.
5. Use `/tdd` — this is build work, not a decision.

## Context

- Shape and structure decided in [11 — Reference project: shape and structure](11-reference-project-shape.md).
- Full classification table: [04 — The change-shape catalogue](04-change-shape-catalogue.md).
- Spike proving the mechanism: [05 — Prove the mechanism](05-prove-the-mechanism.md), branch `prototype/05-mechanism-spike`.
- Public API to build against: [07 — Public API surface](07-public-api-surface.md), [ADR 0002](../../docs/adr/0002-public-api-surface.md).
- Enforced layout to build under: [08 — Enforced layout and the version manifest](08-layout-and-manifest.md), [ADR 0003](../../docs/adr/0003-layout-and-manifest.md).
- Graduated from the map's "Not yet specified: 0.1 build slices" once [11](11-reference-project-shape.md) resolved.
