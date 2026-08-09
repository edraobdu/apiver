# 08 — Enforced layout and the version manifest

Type: grilling
Status: open
Blocked by: 07

## Question

Two coupled decisions. The layout is what makes squash reachable; the manifest is what makes `versions`, gating, and squash possible at all.

### Layout (enforced for authored versions, discovered for the base)

1. What exactly is the enforced structure for a version the developer authors? (`api/v2/serializers.py` + `api/v2/views.py` + `api/v2/registry.py`? Package-per-resource? Something flatter?)
2. **How is it enforced** — a Django system check, an import-time error, a CLI lint, or only a documented convention that `migrate` and `squash` assume? Loud failure vs. quiet assumption is a real DX fork.
3. What does the *discovered* base look like on disk? `migrate` generates one file — where does it go, and is that file hand-editable afterwards or regenerated?
4. Does the layout have to be uniform across versions, or can V1 be discovered-and-scattered while V2 and V3 are authored-and-structured? (The standing decision implies yes — confirm the consequences for squash.)

### Manifest

The manifest is load-bearing for four features: `migrate` writes it, `apiver versions` reads it, version gating reads it, squash reads it at 1.0.

5. **Format and location.** `apiver.toml` at repo root? A section in `pyproject.toml`? A Python module (`versions.py`, as in the original Gemini thread)? Django settings? Trade-off: a Python module can hold class references directly; a TOML file is toolable by a CLI without importing Django.
6. **Contents.** Lineage (which version derives from which), base version, per-version status (`stable` / `deprecated` / `sunset` / `testing`), sunset dates, alias pointers, and — the important one — **the resolution map**: which routes each version overrides, removes, or inherits.
7. **Generated or hand-written?** If generated, when — at `migrate` time, at import time, at CLI invocation? If hand-written, what stops it drifting from the code? A manifest that lies is worse than no manifest.
8. **Is it the source of truth, or a cache?** If the `Version` objects in code disagree with the manifest, which wins, and how is the conflict surfaced? Only one can be authoritative — pick it explicitly (see [07](07-public-api-surface.md) item 5).

## Context

- Settled: layout enforced for authored versions, discovered for the base. `migrate` generates wiring, never moves files.
- Settled: the manifest ships in 0.1, even though its biggest consumer (squash) doesn't arrive until 1.0. Cheap now, expensive to retrofit.
- Feeds [09](09-squash-feasibility.md), which checks whether these two decisions actually make squash reachable.

## Constraint added by [03 — drf-spectacular](03-spectacular-integration.md)

**Version-suffixed class names are load-bearing for schema correctness, not a style preference.** drf-spectacular derives component names from `__class__.__name__` minus `"Serializer"`. Inheritance is fine — `PaymentV2Serializer(PaymentV1Serializer)` yields clean `PaymentV2`/`PaymentV1`. But **two different classes sharing a name** — exactly what `api/v1/serializers.py::PaymentSerializer` plus `api/v2/serializers.py::PaymentSerializer` produces — warns *and emits a silently wrong schema*: the second class is never registered and V2's endpoints `$ref` V1's component (`plumbing.py:797-802`, `openapi.py:1696-1697`).

So the enforced layout must mandate version-suffixed class names even though the directory already separates versions. Decide whether that is enforced by a system check, by a CLI lint, or only documented — and note a related trap: `@extend_schema_serializer` annotations live in a plain class attribute, so an **undecorated subclass silently inherits its parent's `component_name`**.

**Also:** `SCHEMA_PATH_PREFIX` must be pinned per version. Its default auto-estimator is `commonpath` over the document's own paths, so adding a single endpoint can rename every operationId in the file — which would make 0.2's `diff` unusable.
