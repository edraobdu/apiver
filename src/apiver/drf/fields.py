from rest_framework.serializers import Serializer


def check_no_removed_fields(serializer_class: type) -> None:
    """Raise if `serializer_class`'s MRO sets a declared field to `None`.

    `field = None` is DRF's silent footgun (ticket 14, ADR 0006): a `ModelSerializer`
    subclass expecting Django-forms-style removal instead gets the field
    rebuilt fresh from the model, because `Meta.fields` still names it and
    `_declared_fields` no longer does — so it survives, unannounced, in both
    the response body and the schema. On a plain `Serializer` the same
    assignment happens to delete the field via an accident of
    `SerializerMetaclass`'s bookkeeping, which is exactly why it reads as a
    working idiom until the day the class grows a `Meta` and quietly stops
    working. apiver raises unconditionally rather than special-casing the
    one shape where it's harmless — the fix is always the same one line
    (`Meta.fields` surgery, or `del self.fields[...]` in `__init__` for a
    dynamically-computed exclusion).

    Only bare class attributes are considered — nothing inside a nested
    `Meta` is inspected, since `Meta.fields`/`Meta.exclude` are the
    supported removal idioms this guard exists to steer developers toward.
    """
    if not (isinstance(serializer_class, type) and issubclass(serializer_class, Serializer)):
        return

    # `known_fields` accumulates, base-to-derived, every name that is live as
    # a field going into the *next* class in the MRO: explicit Field
    # instances (read off `_declared_fields`, since SerializerMetaclass pops
    # them out of the class `__dict__` itself) and names a ModelSerializer's
    # own `Meta.fields` requests, which is what makes a ModelSerializer
    # rebuild a "removed" field fresh from the model instead of dropping it.
    known_fields: set[str] = set()
    for klass in reversed(serializer_class.__mro__):
        own = vars(klass)

        for name, value in own.items():
            if name == "Meta" or name.startswith("__"):
                continue
            if value is None and name in known_fields:
                raise ValueError(
                    f"{serializer_class.__name__}.{name} is set to None, shadowing the "
                    f"field {klass.__name__} inherits. DRF ignores this outside a plain "
                    "Serializer's single-inheritance case — the field can survive in both "
                    "the response body and the schema. Remove it with Meta.fields surgery "
                    f"(or del self.fields[{name!r}] in __init__ for a dynamically-computed "
                    "exclusion) instead."
                )

        meta = own.get("Meta")
        meta_fields = getattr(meta, "fields", None) if meta is not None else None
        if isinstance(meta_fields, list | tuple):
            known_fields |= set(meta_fields)

        known_fields |= set(own.get("_declared_fields", {}))
