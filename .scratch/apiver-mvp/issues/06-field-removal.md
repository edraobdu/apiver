# 06 — Field removal: the idiom, and whether a helper earns its place

Type: grilling
Status: resolved
Assignee: claude
Blocked by: 04, 05

## Question

Removing a field is the most common breaking API change and the one Python inheritance handles worst. `PaymentV2Serializer(PaymentV1Serializer)` can add and override trivially; subtracting an inherited field requires one of:

- `Meta.fields` surgery — restating the list, or `[f for f in PaymentV1Serializer.Meta.fields if f != "legacy_code"]`
- `Meta.exclude` — but `fields` and `exclude` are mutually exclusive in DRF, so this depends on how the parent declared itself
- `del self.fields["legacy_code"]` in `__init__` — works, invisible to static analysis, and drf-spectacular may or may not see it (check against [03](03-spectacular-integration.md))
- declaring the field as `None` on the subclass — does DRF honour that?

Decide:

1. **What is the recommended idiom?** Pick one and make it the documented way, having actually tried each in [05](05-prove-the-mechanism.md)'s project.
2. **Does the schema see it?** Any idiom that removes a field at runtime but leaves it in the OpenAPI schema is disqualified — it would break `diff`/`check` and the docs at once.
3. **Does the Q6(b) helper earn its place?** The charting session provisionally said yes (a serializer helper for field removal). Now that the idiom is known, confirm or reverse. A helper is only justified if the raw idiom is genuinely bad *and* the helper doesn't drag in a parallel object model — the thing ChatGPT §16/§21 rightly warns against.
4. **If yes, what is it?** A mixin? A `remove_fields = [...]` class attribute? A `derive_serializer()` factory? Whatever it is, it must be inspectable, must not require a metaclass, and must leave normal Python inheritance semantics intact.
5. **Does the same problem exist for viewsets?** Removing an inherited `@action`, or dropping an inherited `permission_class`. Same decision, same bar.

## Context

- Settled: normal Python inheritance semantics apply wherever possible. The strongest selling point is that a V2 serializer is *obvious, inspectable, boring Python*.
- Depends on [04](04-change-shape-catalogue.md) for the full list of removal-shaped changes, and [05](05-prove-the-mechanism.md) for having actually run them.

## Added by [01 — Route identity](01-route-identity.md)

6. **Removing an inherited `@action`.** Deferred here from 01 because it is the same "subtraction under inheritance" problem and deserves one coherent answer across serializer fields, viewset actions, and route entries — not three ad-hoc ones.

   DRF's router discovers extra actions via `get_extra_actions()`, which inspects class members for a `.mapping` attribute. Setting `refund = None` on a V2 subclass will either crash the router or be silently ignored — establish which. Decide between a declaration (`remove_actions = ["refund"]`), a helper, or documenting the workaround (override the method to return 410 Gone).

   Note the interaction with 01's decision that **a whole registration is the unit of override**: an inherited action that V2 wants gone is *not* a route-level removal, because the registration itself survives. It is genuinely a class-level subtraction, which is why it belongs in this ticket rather than in route composition.

## Answer

Verified empirically against Django 6.1 / DRF 3.18 / drf-spectacular 0.30 in an ephemeral `uv` environment before deciding — the premise that idioms had been "actually tried in 05" wasn't true yet (05's spike only exercised a field *type* change, never removal). No code committed; verification only.

1. **Canonical idiom: `Meta.fields` surgery.** `class Meta(Parent.Meta): fields = [f for f in Parent.Meta.fields if f != "removed_field"]`. Confirmed schema-correct — drops from both runtime output and the OpenAPI schema. `del self.fields[...]` in `__init__` is the documented fallback for dynamically-computed exclusions (e.g. depends on `self.context`) — also confirmed schema-correct; drf-spectacular instantiates the serializer to read live `.fields`, so it is **not** invisible to the schema as the question speculated. `Meta.exclude` is **not** a general-purpose idiom: it only composes if the *parent* was declared with `exclude=[...]` instead of `fields=[...]`; mixing inherited `fields` with subclass `exclude` hard-crashes (`AssertionError: Cannot set both 'fields' and 'exclude'`).

2. **Schema visibility: confirmed case by case** (see above) — `Meta.fields` surgery ✅, `del self.fields[...]` ✅, `field = None` ❌ (see below).

3. **No helper.** The raw `Meta.fields` idiom is one readable line, already obvious/inspectable Python. A `remove_fields` mixin or `derive_serializer()` factory would be sugar for something that isn't ugly, and risks the parallel-object-model trap (ChatGPT §16/§21). Reverses the charting session's provisional "yes."

4. N/A — no helper.

5. **Actions: `refund = None` is the idiom, unadorned.** Confirmed `get_extra_actions()` honors `None` cleanly — the action disappears from the router with no crash and no silent survival. Asymmetric with fields (`None` is correct here, broken there) — worth flagging explicitly in docs. No `remove_actions = [...]` declaration needed.

   **`field = None` is a footgun, not an idiom.** Confirmed DRF silently ignores it — the field survives in both runtime serialization and the schema. apiver must guard against this loudly (walk the MRO for serializer fields set to `None` outside `Meta`, raise at class-definition or route-composition time), not just document "don't do this." Same self-verifying-composition pattern ADR 0001 established for routes.

   **`permission_classes`/`filter_backends` subtraction: out of scope.** Plain class-attribute lists — removing an inherited entry is ordinary Python attribute override (`permission_classes = [OtherPermission]`), no DRF gotcha behind it, no library support needed.

6. **Recommended default workflow: deprecate-then-remove, not immediate hard removal.** The README's field-removal story leads with softening in V(n) — `required=False` for request fields, `@extend_schema_serializer(deprecate_fields=[...])` (native drf-spectacular, zero apiver code) for response fields — then hard-removing via idiom (1) in V(n+1) once usage data confirms it's safe. Immediate hard removal stays documented as the fast path for low-stakes/internal fields. Both halves confirmed schema-visible today: `required=False` drops the field from the write schema's `required` list; `deprecate_fields` marks the OpenAPI property `deprecated: true` while the field keeps being returned.

7. **No "phase-out" marker in 0.1.** `required=False` and `deprecate_fields` can't be distinguished from "this field has always been optional" purely from the schema — but adding a marker now, with no `check` (0.2) built yet to consume it, risks guessing wrong about what 0.2 actually needs. Revisit when `check` is built.
