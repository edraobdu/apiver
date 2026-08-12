"""Unit tests for the diff engine itself (ticket #76) — hand-built OpenAPI
document fragments, no Django/DRF app needed since `diff_schemas` operates
on plain dicts."""

from apiver.drf.schema_diff import diff_schemas, format_diff_text, to_jsonable

ORDER_V1 = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "readOnly": True},
        "legacy_id": {"type": "string"},
    },
    "required": ["id"],
}

ORDER_V2 = {
    "type": "object",
    "properties": {
        "id": {"type": "integer", "readOnly": True},
        "order_ref": {"type": "string"},
    },
    "required": ["id", "order_ref"],
}


def _doc(*, paths, components):
    return {"paths": paths, "components": {"schemas": components}}


def test_field_removed_and_added_between_versions():
    old = _doc(
        paths={
            "/api/v/orders/{id}/": {
                "get": {"responses": {"200": {"content": {"application/json": {"schema": ORDER_V1}}}}}
            }
        },
        components={},
    )
    new = _doc(
        paths={
            "/api/v/orders/{id}/": {
                "get": {"responses": {"200": {"content": {"application/json": {"schema": ORDER_V2}}}}}
            }
        },
        components={},
    )

    diff = diff_schemas(old, new)

    removed = {c.field for c in diff.fields if c.kind == "removed"}
    added = {c.field for c in diff.fields if c.kind == "added"}
    assert removed == {"legacy_id"}
    assert added == {"order_ref"}


def test_field_type_change_is_reported_as_changed():
    old = _doc(
        paths={
            "/api/v/orders/{id}/": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": {"total": {"type": "integer"}}}
                                }
                            }
                        }
                    }
                }
            }
        },
        components={},
    )
    new = _doc(
        paths={
            "/api/v/orders/{id}/": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": {"total": {"type": "string"}}}
                                }
                            }
                        }
                    }
                }
            }
        },
        components={},
    )

    diff = diff_schemas(old, new)

    assert len(diff.fields) == 1
    change = diff.fields[0]
    assert change.kind == "changed"
    assert change.before["type"] == "integer"
    assert change.after["type"] == "string"
    assert change.breaking is True


def test_resource_removed_and_added():
    old = _doc(paths={"/api/v/widgets/": {"get": {}}}, components={})
    new = _doc(paths={"/api/v/gadgets/": {"get": {}}}, components={})

    diff = diff_schemas(old, new)

    kinds = {(c.path, c.kind) for c in diff.resources}
    assert ("/api/v/widgets/", "removed") in kinds
    assert ("/api/v/gadgets/", "added") in kinds
    assert all(c.breaking for c in diff.resources if c.kind == "removed")
    assert all(not c.breaking for c in diff.resources if c.kind == "added")


def test_action_removed_is_a_method_level_resource_change():
    old = _doc(paths={"/api/v/orders/{id}/refund/": {"post": {}}}, components={})
    new = _doc(paths={"/api/v/orders/{id}/refund/": {}}, components={})

    diff = diff_schemas(old, new)

    assert diff.resources == [
        type(diff.resources[0])(path="/api/v/orders/{id}/refund/", method="post", kind="removed")
    ]


def test_new_required_request_field_is_breaking_but_new_response_field_is_not():
    old = _doc(
        paths={
            "/api/v/orders/": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {}, "required": []}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "properties": {}, "required": []}
                                }
                            }
                        }
                    },
                }
            }
        },
        components={},
    )
    new = _doc(
        paths={
            "/api/v/orders/": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"note": {"type": "string"}},
                                    "required": ["note"],
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"echo": {"type": "string"}},
                                        "required": [],
                                    }
                                }
                            }
                        }
                    },
                }
            }
        },
        components={},
    )

    diff = diff_schemas(old, new)

    by_field = {(c.direction, c.field): c for c in diff.fields}
    assert by_field[("request", "note")].breaking is True
    assert by_field[("response", "echo")].breaking is False


def test_component_only_changes_are_tracked_separately_from_fields():
    old = _doc(paths={}, components={"Payment": {"type": "object", "properties": {}}})
    new = _doc(paths={}, components={"PaymentV3": {"type": "object", "properties": {}}})

    diff = diff_schemas(old, new)

    kinds = {(c.component, c.kind) for c in diff.components}
    assert kinds == {("Payment", "removed"), ("PaymentV3", "added")}
    assert diff.fields == []


def test_empty_diff_reports_no_changes():
    doc = _doc(paths={"/api/v/ping/": {"get": {}}}, components={})

    diff = diff_schemas(doc, doc)

    assert diff.is_empty
    assert "no schema-visible changes" in format_diff_text(diff, old_name="v1", new_name="v1")


def test_format_diff_text_counts_breaking_changes():
    old = _doc(
        paths={
            "/api/v/orders/{id}/": {
                "get": {"responses": {"200": {"content": {"application/json": {"schema": ORDER_V1}}}}}
            }
        },
        components={},
    )
    new = _doc(
        paths={
            "/api/v/orders/{id}/": {
                "get": {"responses": {"200": {"content": {"application/json": {"schema": ORDER_V2}}}}}
            }
        },
        components={},
    )

    diff = diff_schemas(old, new)
    text = format_diff_text(diff, old_name="v1", new_name="v2")

    assert "breaking change" in text
    assert "legacy_id" in text


def test_to_jsonable_includes_blind_spots_note():
    diff = diff_schemas({"paths": {}, "components": {}}, {"paths": {}, "components": {}})

    payload = to_jsonable(diff)

    assert payload["resources"] == []
    assert "blind_spots" in payload
    assert "SerializerMethodField" in payload["blind_spots"]
