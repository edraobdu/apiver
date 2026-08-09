# 06 — Field removal: the idiom, and whether a helper earns its place

Type: grilling
Status: open
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
