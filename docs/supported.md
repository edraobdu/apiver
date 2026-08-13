# What's Supported

Route composition handles anything routable — ViewSets, `APIView`s, function views, plain Django views
— uniformly. Below is the full change-shape catalogue, including every awkward or schema-invisible case,
not just the easy ones.

| Change | How | Visible in a schema diff? |
| --- | --- | --- |
| Add a field | Declare it on the subclassed serializer | Yes |
| Change type, nullability, validation, choices, read-only | Redeclare the field on the subclass | Yes |
| Remove a field | `Meta.fields` surgery against the parent's list | Yes |
| Rename a field | Add the new name, remove the old — no dedicated rename primitive | Yes, as one field deleted and one added |
| Change a `SerializerMethodField`'s output | Override `get_<field>` | **No** — same schema, different response body |
| Flat fields → nested object | Assemble the nested shape in a `SerializerMethodField`, translate writes back by hand | Yes, if annotated with `@extend_schema_field`; opaque otherwise |
| Add a resource | `register()` | Yes |
| Remove a resource | `remove()` | Yes |
| Change a resource's URL prefix | `remove()` the old key, `register()` the same handler at the new one | Yes |
| Remove an `@action` | Set the action attribute to `None` on the subclass | Yes |
| Change permissions, authentication | Override the ordinary DRF class attribute | Yes, as a class-attribute diff — **No** if computed dynamically (`get_permissions()`) instead |
| Change pagination, filtering, throttling | Override the ordinary DRF class attribute | Yes, as a class-attribute diff — **No** if computed dynamically instead |
| Change default ordering | Override the `ordering` class attribute | Yes, as a class-attribute diff — **No** if computed dynamically (`get_queryset()`) instead |
| Change the error response shape | Override exception handling | **No** — `get_exception_handler()` is a method override, not a class attribute; there's nothing static to diff |

The field-removal story has one sharp edge worth calling out explicitly: **`field = None` does not
remove a field.** It's the idiom every Django-forms developer reaches for, and DRF silently ignores it —
the field survives in both the response and the schema. apiver walks the MRO at `register()`/
`override()` time and raises if it sees this, pointing at `Meta.fields` surgery instead. The
`@action`-removal idiom is the asymmetric exception: `refund = None` on a ViewSet subclass *does*
correctly remove an inherited `@action` — DRF's own `get_extra_actions()` already handles that cleanly.

The recommended default for removing a field a client still depends on is **deprecate, then remove**:
soften it in `V(n)` with `required=False` and drf-spectacular's native `deprecate_fields`, then
hard-remove it in `V(n+1)`. Immediate hard removal stays the documented fast path for low-stakes fields
nobody's realistically depending on.

## The routing/schema boundary

Stated plainly, because a hidden boundary is worse than an honest one: **route composition works for
anything routable. Schema reasoning works only for what drf-spectacular understands.** A bare `APIView`
with no `serializer_class` routes correctly under every version and does appear in its OpenAPI document
— just with a thin, degraded entry (no request/response body shape) instead of a real one. This isn't a
gap apiver is hiding; it's a property of drf-spectacular's own introspection, and apiver doesn't try to
paper over it with guesswork.

The same honesty extends to the remaining **No** rows in the table above — `SerializerMethodField`
output and error response shape. They're real, supported changes; a schema diff can't see them by
construction, not a gap apiver is hiding, and neither is even in principle a static class attribute
apiver could diff instead: the first is arbitrary Python inside `get_<field>`, the second is a
`get_exception_handler()` method override. `permission_classes`, `authentication_classes`,
`pagination_class`, `filter_backends`, `throttle_classes`, and `ordering` turned out not to need the
schema at all: they're ordinary class attributes, so `apiver diff`/`apiver check` compare them directly
off each version's registered handler — reported as `attributes` alongside the schema-derived
`fields`/`resources`. This only catches the ordinary class-attribute override idiom; a view that
computes the equivalent behavior dynamically (`get_permissions()`, `get_queryset()`) is still invisible,
the same way the remaining **No** rows are.

If you're not using drf-spectacular at all, route composition still works exactly as described above —
every version still resolves and serves correctly. What you lose is everything in this page and in
`apiver diff`/`apiver check`: per-version schema documents, and any tooling that reasons about what
changed between two versions. Routing and schema are deliberately separable; only the schema half
depends on drf-spectacular.
