---
status: accepted
---

# Field removal: `field = None` raises, `Meta.fields` surgery is the canonical idiom

Subtraction is where the inheritance model apiver builds on is weakest. Route removal (ADR 0002 item 4)
already raises loudly on misuse; serializer field removal has no such guard on the DRF side, and DRF's own
behavior actively misleads a developer coming from Django forms.

## The footgun

`field = None` on a serializer subclass looks like it should remove an inherited field — it's the
Django-forms idiom. DRF's `SerializerMetaclass` only pops `Field` *instances* out of a class's own
`__dict__` into `_declared_fields`; a bare `None` assignment is left alone and simply excluded from that
one class's own contribution. For a single-inheritance plain `Serializer`, this happens to work: the name
never resurfaces, because nothing else asks for it by name.

For `ModelSerializer`, it doesn't. `get_field_names()` reads the field list from `Meta.fields`, which is an
ordinary Python class attribute — not automatically merged across subclasses unless the subclass explicitly
subclasses its parent's `Meta`. A subclass that sets `internal_note = None` without touching `Meta` leaves
`Meta.fields` pointing at the parent's list, unchanged, still naming `internal_note`. Since the field is no
longer in `_declared_fields`, `get_fields()` falls through to `build_field()` and reconstructs it fresh from
the model — same name, freshly rebuilt, present in both the response body and the OpenAPI schema. Confirmed
empirically against DRF 3.18: the field survives, silently.

## Decision

1. **`register()` and `override()` raise if the handler's `serializer_class` sets a field to `None` anywhere
   in its MRO, outside a nested `Meta`.** apiver walks the MRO base-to-derived, tracking two sources of
   "this name is currently a live field": `_declared_fields` (already correctly reduced by DRF's own
   metaclass, class by class) and the `fields` list of each class's *own* `Meta`, if it declares one. A bare
   `name = None` on a class whose ancestors put `name` in either set raises `ValueError`, pointing at the
   working idioms.

2. **The check is unconditional — it does not special-case the plain-`Serializer` shape where the
   assignment happens to work.** Relying on it is still wrong: the class is one `Meta` away from silently
   breaking, and a developer reading the code has no way to tell which shape they're looking at. "Footgun,
   not idiom" is a blanket rule, not a per-subclass judgment call.

3. **`action = None` is not this guard, and is explicitly correct.** `ViewSetMixin.get_extra_actions()`
   resolves attributes with `getmembers(cls, _is_extra_action)` — a subclass setting `action_name = None`
   makes `getattr(cls, action_name)` return `None`, which fails the `_is_extra_action` check and drops
   cleanly out of `get_extra_actions()`. No crash, no silent survival, no schema leftover. This asymmetry
   with fields is the single most confusing thing in the removal story and is recorded here so it never gets
   "fixed" into matching field behavior by mistake.

4. **The canonical field-removal idiom is `Meta.fields` surgery** — a subclass declares its own `Meta`
   (typically `class Meta(Parent.Meta): fields = [...]`) with the name dropped from the list. Confirmed
   schema-correct: drf-spectacular instantiates the serializer to build the schema, so it sees exactly the
   same `.fields` a request would.

5. **`del self.fields[...]` in `__init__` is the documented fallback**, for exclusions that depend on
   `self.context` (a request-scoped condition `Meta.fields` can't express statically). Also schema-correct,
   for the same reason as item 4 — and also the reason it's the one shape squash (ADR 0004) can't mechanically
   flatten, since it depends on runtime context.

6. **`Meta.exclude` is not treated as a general-purpose idiom, and this guard does not reason about it.** It
   only composes if the parent itself was declared with `exclude=`, and mixing an inherited `fields` with a
   subclass `exclude` hard-crashes in DRF itself. Detecting misuse here would require resolving the full
   model field set, which this guard deliberately doesn't do — `exclude` composition remains something a
   developer reasons about directly, not something apiver can safely check statically.

7. **No removal helper ships.** The raw `Meta.fields` idiom is one readable, greppable line; a mixin or
   factory (`class Meta: fields = drop(Parent.Meta.fields, "internal_note")`) would be sugar for something
   that isn't ugly, and would give squash a second thing to special-case.

## Considered options

- **Detect only the `ModelSerializer` case**, leaving plain `Serializer` subclasses unchecked since the
  assignment happens to work there. Rejected: it would make the guard's behavior depend on a class's exact
  shape rather than on the idiom used, which is precisely the kind of "works today, breaks on refactor"
  trap this ticket exists to close.
- **Resolve `Meta.exclude` by introspecting the model.** Rejected for this guard: it would need the same
  model-field enumeration `ModelSerializer.get_field_names()` does, at class-registration time, for a mode
  this ADR already treats as unsupported for general removal. Scope stays at what's statically checkable.
- **A metaclass or base-serializer class that intercepts `field = None` at class-definition time.** Rejected:
  it would require every developer's serializer to subclass an apiver-owned base, contradicting the promise
  that a version delta is an ordinary Python subclass of the developer's own code.

## Consequences

The guard only fires when apiver actually sees the serializer — at `register()`/`override()`, via the
handler's `serializer_class` attribute. A serializer never wired to a Version (or reached only through
`get_serializer_class()` dynamic dispatch) is not checked; this is the same boundary `_check_suffix` (ADR
0003 item 2) already accepts for the same reason — apiver reasons about what it composes, not about
arbitrary code it never sees.
