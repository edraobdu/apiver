# 11 — Reference project: shape and structure

Type: grilling
Status: open
Blocked by: —

## Question

[04](04-change-shape-catalogue.md) enumerated and classified every change-shape apiver claims to handle (22 rows: field-level, resource-level, behavioral). The destination requires this catalogue to become a real reference DRF project — "if a change-shape isn't in that project, the library doesn't support it." This ticket decides how the catalogue becomes that project, not the project's code.

Decide:

1. **Granularity.** One resource per change-shape (22 small, isolated resources, each showing exactly one thing changing) vs. a smaller set of realistic resources (e.g. `users`/`payments`/`orders`, as in [05](05-prove-the-mechanism.md)) each carrying several change-shapes at once, closer to a real app. Trade-off: isolation for teaching clarity vs. realism for credibility ("does this hold up on an app that looks like mine").

2. **Coverage of the 🟡/🔴 rows.** Rows 5, 6, 9, 13, 14b (awkward) and row 10 (undetectable) are the ones that carry the "name the 20%" pitch. Does the reference project visibly demonstrate the documented idiom for each — including the ones whose idiom is still pending [06](06-field-removal.md)?

3. **Does it double as the drf-spectacular correctness demo?** The destination's schema story (`/api/v2/docs` showing a complete, correct V2) is sold on this same project, per [03](03-spectacular-integration.md). Confirm one project serves both purposes rather than building two.

4. **Relationship to [05](05-prove-the-mechanism.md).** Is 05's throwaway spike the seed this project grows from (promoted from throwaway to permanent once proven), or a separate one-off discarded once its questions are answered?

5. **When is it actually built?** This ticket produces the plan only. The code itself needs [07](07-public-api-surface.md)'s override/remove syntax and [08](08-layout-and-manifest.md)'s enforced layout to exist first, so actual construction is a build ticket sequenced after those — confirm that sequencing.

## Context

- Full classification table: [04 — The change-shape catalogue](04-change-shape-catalogue.md).
- Standing decision (map): route composition works for anything; schema reasoning only for what drf-spectacular understands — the reference project is where that boundary becomes visible.
- Graduated from the map's "Not yet specified: Reference-project construction."
