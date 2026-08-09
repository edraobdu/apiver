# 04 — The change-shape catalogue

Type: grilling
Status: open
Blocked by: —

## Question

**This is the spec.** The destination includes a reference DRF project enumerating every kind of API change apiver claims to handle. This ticket produces the catalogue that project is built from — and, more importantly, honestly marks which shapes the inheritance model handles well, which are awkward, and which it cannot express at all.

The strongest pitch for deltas-forward is *"10% of Stripe's complexity, covers 80% of real version changes."* That pitch is only credible if you can name the 20% it doesn't cover. This ticket names it.

For each change-shape below (extend the list), decide: **supported cleanly / awkward but possible / not supported**, and for anything not "clean", write the idiom a developer would actually use.

**Field-level**
- Add an optional response field
- Add a required request field
- Change a field's type (`IntegerField` → `DecimalField`)
- Change nullability or required-ness
- Rename a field
- **Remove a field** — the single most common breaking change, and the one Python inheritance handles worst
- Change a field's validation rules
- Change enum/choices membership
- Restructure nesting (flat → nested object, or a nested object flattened)
- Change a `SerializerMethodField`'s computed output

**Resource-level**
- Add a whole new resource in V2
- **Remove a resource in V2** (`/api/v1/legacy-invoices` must not exist in V2)
- Change a resource's URL prefix / path
- Add, change, or **remove** an `@action`
- Change permissions / authentication on an endpoint
- Change pagination style or default page size
- Change filtering / ordering / search params
- Change default ordering (a *silent* behavioural break — no schema change at all)
- Change error response shape or status codes

For each, also note: **would `check` be able to detect it as breaking by diffing OpenAPI schemas?** Some (default ordering, pagination defaults, changed `SerializerMethodField` logic) produce no schema delta at all — those are the honest blind spots of the schema-diff approach chosen for 0.2.

Output: a table in this ticket's Answer, which becomes the build plan for the reference project and the feature matrix in the README.

## Context

- Settled: field removal gets a library helper if it earns one — see [06](06-field-removal.md).
- Settled: route-level `remove()` is non-negotiable.
- Settled: model/database-layer drift is out of scope (see map). Field removals *driven by a dropped column* are still in scope as an API-surface change; the DB side is not.
