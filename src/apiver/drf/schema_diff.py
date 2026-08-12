"""Schema-diff-based breaking-change detection (ticket #76).

`apiver diff V1 V2` compares two versions' composed OpenAPI schemas —
built the same way each version already serves its own `schema_view()`
over HTTP — and reports what changed, anchored to the same change-shape
catalogue the README's support matrix already documents as schema-visible:
field add/remove/type/nullability/validation/choices, resource add/remove,
URL prefix change (shows as one path removed, one added — no dedicated
rename primitive, matching how a field rename already has none either),
and `@action` removal.

Diffing is anchored to routes (`(path, method)`), not to component schema
names: an overridden resource commonly gets a *different* auto-generated
component name from its parent (e.g. `Payment` -> `PaymentV3`, see
`test_version_schema.py`), so comparing components by name would report
"Payment removed, PaymentV3 added" instead of the field-level change a
human actually wants to see. Resolving each operation's request/response
body through its `$ref` and diffing the resulting property sets sidesteps
that entirely.

Four of the support matrix's **No** rows turn out not to need the schema at
all (ticket #79): `permission_classes`, `authentication_classes`,
`pagination_class`, `filter_backends`, and `throttle_classes` are ordinary
class attributes, resolved by plain Python attribute lookup — inheritance
already does the MRO walk, so `getattr(handler, "permission_classes")`
returns the effective value whether a version's handler declared it itself
or inherited it untouched. `diff_view_attributes` compares that value
between each version's registered handler for the same registration key,
straight off the live `Version` objects, no schema involved. What's still
out of reach, by construction — arbitrary Python inside `get_<field>`, a
`get_permissions()`/`get_queryset()` override, exception-handler
substitution, none of which is a static class attribute — stays disclaimed
via `BLIND_SPOTS_NOTE`, so a clean report can never be mistaken for
"nothing changed."
"""

from dataclasses import dataclass, field, replace
from typing import Any

from django.conf import settings

from ..schemes import Scheme
from .version import Version

__all__ = [
    "ATTRIBUTE_DIFF_KEYS",
    "AttributeChange",
    "BLIND_SPOTS_NOTE",
    "ComponentChange",
    "DiffError",
    "FieldChange",
    "ResourceChange",
    "SchemaDiff",
    "diff_schemas",
    "diff_versions",
    "diff_view_attributes",
    "format_diff_text",
    "get_schema",
    "to_jsonable",
]


class DiffError(RuntimeError):
    """A version's composed schema could not be built for diffing."""


BLIND_SPOTS_NOTE = (
    "apiver: a schema diff can't see everything — SerializerMethodField output changes and "
    "error response shape changes are real, supported changes that don't appear in an OpenAPI "
    "diff by construction (drf-spectacular doesn't introspect them, and neither is a static "
    "class attribute apiver can diff). permission_classes, authentication_classes, "
    "pagination_class, filter_backends, throttle_classes, and ordering are diffed as class "
    "attributes (see 'attributes' below) when overridden the ordinary way — but not when a view "
    "computes the equivalent behavior dynamically instead (get_permissions(), get_queryset()). "
    "See README's support matrix."
)

# The class attributes `diff_view_attributes` compares — the ordinary DRF
# override idiom for each of the support matrix's permissions/authentication,
# pagination/filtering/throttling, and default-ordering rows (ticket #79).
# `ordering` is what `rest_framework.filters.OrderingFilter.get_default_ordering`
# reads off the view — a plain class attribute like the rest, unlike
# SerializerMethodField output or error response shape (see BLIND_SPOTS_NOTE),
# neither of which is an attribute at all. Plain `getattr` already resolves
# these through the handler's MRO, so no manual walk is needed the way
# `check_no_removed_fields` needs one for `field = None`.
ATTRIBUTE_DIFF_KEYS = (
    "permission_classes",
    "authentication_classes",
    "pagination_class",
    "filter_backends",
    "throttle_classes",
    "ordering",
)

# The JSON Schema keywords a field-level change actually cares about — type,
# nullability, validation, choices, read-only (the README's own change-shape
# wording) — plus "required" membership, folded in separately below since
# it lives on the parent object, not the field itself.
_RELEVANT_KEYWORDS = (
    "type",
    "format",
    "nullable",
    "enum",
    "readOnly",
    "writeOnly",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
)


@dataclass(frozen=True)
class FieldChange:
    """One field's addition, removal, or attribute change within a single
    operation's request or response body."""

    path: str
    method: str
    direction: str  # "request" | "response"
    field: str
    kind: str  # "added" | "removed" | "changed"
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    @property
    def breaking(self) -> bool:
        """Conservative default: anything a client might already depend on
        disappearing or narrowing is breaking; a field merely appearing is
        breaking only when it lands on a request body as required — an
        existing caller's request, sent exactly as before, would now fail
        validation."""
        if self.kind == "removed":
            return True
        if self.kind == "changed":
            return True
        return self.direction == "request" and bool((self.after or {}).get("required"))


@dataclass(frozen=True)
class ResourceChange:
    """One path gaining or losing an operation, or disappearing/appearing
    entirely."""

    path: str
    method: str | None  # None: every operation on this path (whole resource)
    kind: str  # "added" | "removed"

    @property
    def breaking(self) -> bool:
        return self.kind == "removed"


@dataclass(frozen=True)
class ComponentChange:
    """A component schema (drf-spectacular's per-serializer shape) that
    exists on only one side — informational only: routes, not components,
    are diff's anchor (see module docstring), so this rarely corresponds
    1:1 to a field change already reported elsewhere."""

    component: str
    kind: str  # "added" | "removed"


@dataclass(frozen=True)
class AttributeChange:
    """One registration's `permission_classes`/`authentication_classes`/
    `pagination_class`/`filter_backends`/`throttle_classes` resolving to a
    different value between two versions' handler for the same registration
    key (ticket #79) — the whole registration's behavior, not one method,
    since these attributes govern the handler as a whole rather than a
    single (path, method) operation."""

    resource: str  # the Registration key (router prefix, or literal path for a view)
    attribute: str
    before: tuple[str, ...] | str | None
    after: tuple[str, ...] | str | None

    @property
    def breaking(self) -> bool:
        """Conservative default, same posture as `FieldChange`: apiver
        can't know whether a permission/pagination/throttle change loosens
        or tightens behavior, so any change is flagged rather than silently
        assumed safe."""
        return True


@dataclass(frozen=True)
class SchemaDiff:
    resources: list[ResourceChange] = field(default_factory=list)
    components: list[ComponentChange] = field(default_factory=list)
    fields: list[FieldChange] = field(default_factory=list)
    attributes: list[AttributeChange] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.resources or self.components or self.fields or self.attributes)

    @property
    def breaking_changes(self) -> list[ResourceChange | FieldChange | AttributeChange]:
        return [change for change in (*self.resources, *self.fields, *self.attributes) if change.breaking]


def _schema_prefix(version: Version, *, scheme: Scheme) -> str:
    root_prefix: str | None = getattr(settings, "APIVER_ROOT_PREFIX", None)
    if not root_prefix:
        raise DiffError(
            "APIVER_ROOT_PREFIX is not set — apiver doesn't know the absolute URL path a "
            "version's schema is served from (ADR 0007 item 6)."
        )
    try:
        display_name = scheme.format(version.name)
    except ValueError as exc:
        raise DiffError(
            f"version {version.name!r} does not conform to the configured version scheme: {exc}"
        ) from exc
    return root_prefix.lstrip("/") + f"{display_name}/"


def get_schema(version: Version, *, scheme: Scheme) -> dict[str, Any]:
    """The composed OpenAPI schema `version` would serve over HTTP,
    generated directly from the same `SpectacularAPIView` config
    `schema_view()` already builds — bypassing the view's own
    request/permission dispatch (there's no request in reach; `diff`/
    `check` run offline, the same posture `manifest`/`versions` already
    take toward live objects) rather than simulating an HTTP request that
    could 403 against a project's own `SERVE_PERMISSIONS`.

    `schema_view()` derives its prefix independently here rather than
    depending on the project's own urls.py having called it already
    (ADR 0007 item 6's `APIVER_ROOT_PREFIX + display_name` convention,
    also used by `apiver init`/`apiver mount`) — `diff`/`check` only need
    a version's `registry.py` importable, not its Aggregation Root mount.
    """
    view = version.schema_view(prefix=_schema_prefix(version, scheme=scheme))
    generator_class = view.cls.generator_class
    patterns = view.initkwargs["patterns"]
    custom_settings = view.initkwargs.get("custom_settings") or {}
    from drf_spectacular.settings import patched_settings

    with patched_settings(custom_settings):
        generator = generator_class(
            urlconf=None, api_version=custom_settings.get("VERSION"), patterns=patterns
        )
        return generator.get_schema(request=None, public=True)


def _strip_version_prefix(schema: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Every path in a version's composed schema carries its own absolute
    mount prefix (`/api/v1/payments/`, `/api/v2/payments/`) — comparing
    two versions' raw path strings would report every single route as
    "removed, then re-added under a new path" even when nothing about the
    route changed. Stripping each side's own prefix first (`payments/`)
    lets `diff_schemas` match the same route across versions and see only
    what actually changed."""
    absolute_prefix = "/" + prefix.strip("/") + "/"
    paths = schema.get("paths", {})
    normalized = {
        (path[len(absolute_prefix) :] if path.startswith(absolute_prefix) else path): operations
        for path, operations in paths.items()
    }
    return {**schema, "paths": normalized}


def _class_ref(obj: Any) -> str:
    return f"{obj.__module__}.{obj.__qualname__}" if isinstance(obj, type) else str(obj)


def _normalize_attribute_value(value: Any) -> tuple[str, ...] | str | None:
    """`permission_classes`/`authentication_classes`/`pagination_class`/
    `filter_backends`/`throttle_classes` hold classes; `ordering` holds
    plain field-name strings (e.g. `("-created",)`) — `_class_ref` renders
    a class as its qualified name and passes a string through unchanged, so
    both attribute shapes normalize to something JSON-serializable and
    comparable across versions."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return tuple(_class_ref(item) for item in value)
    return _class_ref(value)


def _registrations_by_key(version: Version) -> dict[str, Any]:
    return {
        route.registration.key: route.registration
        for route in version.resolution_table.values()
        if route.registration is not None
    }


def diff_view_attributes(old: Version, new: Version) -> list[AttributeChange]:
    """Compare `ATTRIBUTE_DIFF_KEYS` between `old` and `new`'s handler for
    every registration key present on both sides (ticket #79).

    A registration a version never touched is inherited as the identical
    Python object (ADR 0002 item 2), so `old_handler is new_handler` short-
    circuits the whole comparison for the common case — most routes in a
    delta chain — without walking any attributes at all. Only class-based
    handlers are inspected; a function-based view (a bare `@api_view` or a
    plain Django `View`) has no class attributes to diff, so it's skipped
    the same way it's skipped by `Version._check_no_removed_fields`.
    """
    old_registrations = _registrations_by_key(old)
    new_registrations = _registrations_by_key(new)

    changes: list[AttributeChange] = []
    for key in sorted(set(old_registrations) & set(new_registrations)):
        old_handler = old_registrations[key].handler
        new_handler = new_registrations[key].handler
        if old_handler is new_handler:
            continue
        if not (isinstance(old_handler, type) and isinstance(new_handler, type)):
            continue

        for attribute in ATTRIBUTE_DIFF_KEYS:
            before = _normalize_attribute_value(getattr(old_handler, attribute, None))
            after = _normalize_attribute_value(getattr(new_handler, attribute, None))
            if before != after:
                changes.append(AttributeChange(resource=key, attribute=attribute, before=before, after=after))
    return changes


def diff_versions(old: Version, new: Version, *, scheme: Scheme) -> SchemaDiff:
    """Build both versions' composed schemas and diff them, prefix-stripped
    so routes line up across versions regardless of which version segment
    each one is actually mounted under — the convenience entry point `diff`/
    `check` use instead of composing `get_schema`/`diff_schemas` by hand.

    Attribute changes (`diff_view_attributes`) are folded in here rather
    than into `diff_schemas` itself, since they're read straight off the
    live `Version`/handler objects, not the composed OpenAPI documents
    `diff_schemas` operates on — `diff_schemas` stays schema-only and
    testable against hand-built document fragments with no Django app in
    reach."""
    old_prefix = _schema_prefix(old, scheme=scheme)
    new_prefix = _schema_prefix(new, scheme=scheme)
    old_schema = _strip_version_prefix(get_schema(old, scheme=scheme), old_prefix)
    new_schema = _strip_version_prefix(get_schema(new, scheme=scheme), new_prefix)
    diff = diff_schemas(old_schema, new_schema)
    return replace(diff, attributes=diff_view_attributes(old, new))


def _resolve_body(schema: dict[str, Any] | None, components: dict[str, Any]) -> dict[str, Any] | None:
    """Follow `$ref`/array/pagination wrapping down to the object schema a
    field-level diff can actually walk `properties`/`required` on.
    Stops at one level of a `results`-shaped pagination wrapper (the
    default DRF paginators' shape); a project's custom paginator may wrap
    differently, in which case the field diff simply finds nothing to
    compare — consistent with pagination already being a schema-diff blind
    spot (`BLIND_SPOTS_NOTE`), not a silent wrong answer."""
    if schema is None:
        return None
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        return components.get(name)
    if schema.get("type") == "array" and "items" in schema:
        return _resolve_body(schema["items"], components)
    properties = schema.get("properties", {})
    if "results" in properties:
        return _resolve_body(properties["results"], components)
    return schema


def _body_schema(operation: dict[str, Any], *, direction: str) -> dict[str, Any] | None:
    if direction == "request":
        content = operation.get("requestBody", {}).get("content", {})
    else:
        responses = operation.get("responses", {})
        ok_status = next((status for status in sorted(responses) if status.startswith("2")), None)
        if ok_status is None:
            return None
        content = responses[ok_status].get("content", {})
    return content.get("application/json", {}).get("schema")


def _field_attrs(field_schema: dict[str, Any], *, required: bool) -> dict[str, Any]:
    attrs = {key: field_schema[key] for key in _RELEVANT_KEYWORDS if key in field_schema}
    attrs["required"] = required
    return attrs


def _diff_operation_fields(
    path: str,
    method: str,
    direction: str,
    old_op: dict[str, Any],
    new_op: dict[str, Any],
    *,
    old_components,
    new_components,
) -> list[FieldChange]:
    old_resolved = _resolve_body(_body_schema(old_op, direction=direction), old_components)
    new_resolved = _resolve_body(_body_schema(new_op, direction=direction), new_components)
    if old_resolved is None and new_resolved is None:
        return []

    old_props: dict[str, Any] = (old_resolved or {}).get("properties", {})
    new_props: dict[str, Any] = (new_resolved or {}).get("properties", {})
    old_required = set((old_resolved or {}).get("required", []))
    new_required = set((new_resolved or {}).get("required", []))

    changes: list[FieldChange] = []
    old_field_keys, new_field_keys = set(old_props), set(new_props)
    for name in sorted(old_field_keys - new_field_keys):
        changes.append(FieldChange(path=path, method=method, direction=direction, field=name, kind="removed"))
    for name in sorted(new_field_keys - old_field_keys):
        after = _field_attrs(new_props[name], required=name in new_required)
        changes.append(
            FieldChange(path=path, method=method, direction=direction, field=name, kind="added", after=after)
        )
    for name in sorted(old_field_keys & new_field_keys):
        before = _field_attrs(old_props[name], required=name in old_required)
        after = _field_attrs(new_props[name], required=name in new_required)
        if before != after:
            changes.append(
                FieldChange(
                    path=path,
                    method=method,
                    direction=direction,
                    field=name,
                    kind="changed",
                    before=before,
                    after=after,
                )
            )
    return changes


def diff_schemas(old: dict[str, Any], new: dict[str, Any]) -> SchemaDiff:
    """Structured diff between two composed OpenAPI documents — the engine
    behind both `apiver diff` and `apiver check`."""
    old_paths: dict[str, Any] = old.get("paths", {})
    new_paths: dict[str, Any] = new.get("paths", {})
    old_components: dict[str, Any] = old.get("components", {}).get("schemas", {})
    new_components: dict[str, Any] = new.get("components", {}).get("schemas", {})

    resources: list[ResourceChange] = []
    fields: list[FieldChange] = []

    # Each key set built once and reused across its removed/added/shared
    # comparisons below, rather than re-deriving `set(old_paths)`/
    # `set(new_paths)` (and their per-path method equivalents) three times
    # over — the same total path/method/component count is walked either
    # way, just without redoing the set construction per comparison.
    old_path_keys, new_path_keys = set(old_paths), set(new_paths)
    for path in sorted(old_path_keys - new_path_keys):
        resources.append(ResourceChange(path=path, method=None, kind="removed"))
    for path in sorted(new_path_keys - old_path_keys):
        resources.append(ResourceChange(path=path, method=None, kind="added"))

    for path in sorted(old_path_keys & new_path_keys):
        old_methods = {m for m in old_paths[path] if m != "parameters"}
        new_methods = {m for m in new_paths[path] if m != "parameters"}
        for method in sorted(old_methods - new_methods):
            resources.append(ResourceChange(path=path, method=method, kind="removed"))
        for method in sorted(new_methods - old_methods):
            resources.append(ResourceChange(path=path, method=method, kind="added"))
        for method in sorted(old_methods & new_methods):
            old_op, new_op = old_paths[path][method], new_paths[path][method]
            for direction in ("request", "response"):
                fields.extend(
                    _diff_operation_fields(
                        path,
                        method,
                        direction,
                        old_op,
                        new_op,
                        old_components=old_components,
                        new_components=new_components,
                    )
                )

    components: list[ComponentChange] = []
    old_component_keys, new_component_keys = set(old_components), set(new_components)
    for name in sorted(old_component_keys - new_component_keys):
        components.append(ComponentChange(component=name, kind="removed"))
    for name in sorted(new_component_keys - old_component_keys):
        components.append(ComponentChange(component=name, kind="added"))

    return SchemaDiff(resources=resources, components=components, fields=fields)


def to_jsonable(diff: SchemaDiff) -> dict[str, Any]:
    return {
        "resources": [
            {"path": c.path, "method": c.method, "kind": c.kind, "breaking": c.breaking}
            for c in diff.resources
        ],
        "components": [{"component": c.component, "kind": c.kind} for c in diff.components],
        "fields": [
            {
                "path": c.path,
                "method": c.method,
                "direction": c.direction,
                "field": c.field,
                "kind": c.kind,
                "before": c.before,
                "after": c.after,
                "breaking": c.breaking,
            }
            for c in diff.fields
        ],
        "attributes": [
            {
                "resource": c.resource,
                "attribute": c.attribute,
                "before": c.before,
                "after": c.after,
                "breaking": c.breaking,
            }
            for c in diff.attributes
        ],
        "blind_spots": BLIND_SPOTS_NOTE,
    }


def format_diff_text(diff: SchemaDiff, *, old_name: str, new_name: str) -> str:
    lines = [f"== {old_name} -> {new_name} schema diff =="]
    if diff.is_empty:
        lines.append("(no schema-visible changes)")
        return "\n".join(lines) + "\n"

    for change in diff.resources:
        marker = "-" if change.kind == "removed" else "+"
        target = change.path if change.method is None else f"{change.method.upper()} {change.path}"
        lines.append(f"{marker} {target}")

    for change in diff.fields:
        location = f"{change.method.upper()} {change.path} ({change.direction})"
        if change.kind == "removed":
            lines.append(f"- field {change.field!r} removed — {location}")
        elif change.kind == "added":
            lines.append(f"+ field {change.field!r} added — {location}")
        else:
            lines.append(f"~ field {change.field!r} changed — {location}: {change.before} -> {change.after}")

    for change in diff.components:
        marker = "-" if change.kind == "removed" else "+"
        lines.append(f"{marker} component {change.component!r}")

    for change in diff.attributes:
        lines.append(
            f"~ {change.attribute} changed on {change.resource!r}: {change.before} -> {change.after}"
        )

    breaking_count = len(diff.breaking_changes)
    if breaking_count:
        lines.append(f"apiver: {breaking_count} breaking change(s) detected.")
    else:
        lines.append("apiver: no breaking changes detected.")

    return "\n".join(lines) + "\n"
