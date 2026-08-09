# 04 — The change-shape catalogue

Type: grilling
Status: resolved
Blocked by: —
Assignee: claude

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

## Answer

Classification and diff-visibility are tracked as **two separate columns**, not one: several rows are trivial to *write* via plain inheritance but invisible to schema-diff, and collapsing that distinction would either mislabel an easy change as "unsupported" or hide a real blind spot behind a "clean" label. This split is what makes the "name the 20%" pitch honest.

| # | Change-shape | Classification | Idiom | diff-visible? |
|---|---|---|---|---|
| 1 | Add optional response field | 🟢 clean | subclass adds field | ✅ |
| 2 | Add required request field | 🟢 clean | subclass adds field | ✅ |
| 3 | Change field type | 🟢 clean | redeclare field on subclass | ✅ |
| 4 | Change nullable/required | 🟢 clean | redeclare field on subclass | ✅ |
| 5 | Rename a field | 🟡 awkward | add new field (clean) + remove old (idiom → [06](06-field-removal.md)); no separate mechanism needed | ✅ but reported as delete+add, not rename |
| 6 | Remove a field | 🟡 awkward | idiom pending [06](06-field-removal.md) | ✅ |
| 7 | Change validation rules | 🟢/🟡 | redeclare field/validators | partial — declarative constraints (`max_length`, etc.) yes, custom `validate_*` logic no |
| 8 | Change enum/choices | 🟢 clean | redeclare field | ✅ |
| 9 | Restructure nesting (flat↔nested) | 🟡 awkward | redeclare field as nested/flat + possible method overrides | ✅ (type changes) |
| 10 | Change `SerializerMethodField` output | 🟢 to write / 🔴 to detect | override `get_<field>` | ❌ |
| 11 | Add new resource | 🟢 clean | new registration in V2 | ✅ |
| 12 | Remove a resource | 🟢 clean | `v2.remove(prefix)` | ✅ |
| 13 | Change URL prefix/path | 🟡 awkward | remove old + add new — no first-class "move" primitive in 0.1; accepted since it costs nothing new, but it's a known 0.2 `diff`-heuristic gap (bigger than field rename: drops a whole resource's route history, not just one field) | ✅ but as delete+add, loses history |
| 14 | Add/change `@action` | 🟢 clean | inheritance / method override | ✅ |
| 14b | Remove `@action` | 🟡 awkward | idiom pending [06](06-field-removal.md) | ✅ |
| 15 | Change permissions/auth | 🟢 clean | override `permission_classes` | mostly ❌ |
| 16 | Change pagination | 🟢 clean | override `pagination_class`/`page_size` | partial |
| 17 | Change filtering/ordering/search | 🟢 clean | override `filter_backends`/`filterset_class` | partial |
| 18 | Change default ordering | 🟢 clean | override `Meta.ordering`/`get_queryset` | ❌ — silent behavioural break, no schema delta at all |
| 19 | Change error shape/status codes | 🟢 clean | override `get_exception_handler()` per view (DRF supports this per-class); documented alternative is a shared version-aware handler for teams that already centralize error shaping | mostly ❌ |
| 20 | Throttling changes | 🟢 clean | override `throttle_classes` | mostly ❌ |
| 21 | Content negotiation/renderer changes | 🟢 clean | override `renderer_classes` | partial — response media type shows in schema if it changes, custom renderer behavior doesn't |
| 22 | Read-only/writable toggle | 🟢 clean | redeclare field with `read_only=`/`write_only=` | ✅ |

**The honest 20%, in one line:** almost everything is clean by plain Python/DRF inheritance; what isn't clusters in two places — *subtraction* (rows 5, 6, 13, 14b, all resolving through ticket 06's removal idiom) and *diff blind spots* (rows 10, 15–20, trivial to write, invisible to schema-diff, so `check` in 0.2 can't catch them as breaking).

Rows 20–22 (throttling, content negotiation, read-only/writable toggle) were added during this session, beyond the ticket's original list; bulk-endpoint shape changes were considered and left out, since they decompose into rows already covered (add/remove fields, add/remove actions) rather than being a distinct shape.
