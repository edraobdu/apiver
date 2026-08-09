# 03 — drf-spectacular: per-version schemas without collisions

Type: research
Status: resolved
Blocked by: —

## Question

The OpenAPI story is the demo that sells apiver: `/api/v2/docs` shows a *complete, correct* V2 API when the developer only wrote two classes. It's also load-bearing for 0.2, since `diff` and `check` will diff generated schemas rather than parse source.

This ticket establishes how drf-spectacular actually has to be driven to make that work.

Establish, with citations to drf-spectacular's source and docs (note the version):

1. **Per-version schema generation.** How do you produce a separate schema document per version? `SchemaGenerator(urlconf=...)`, `patterns=`, `SERVE_URLCONF`, preprocessing hooks, `SpectacularAPIView` per version — what's the supported route and what are the trade-offs?
2. **Operation IDs.** How are they derived by default? What happens when the *same* viewset class is mounted under both `/api/v1/` and `/api/v2/` — do you get a duplicate-operationId collision, a warning, or silent overwrite? What is the supported hook to suffix or namespace them per version (`get_operation_id`, `OpenApiViewExtension`, `postprocess_hooks`, `@extend_schema(operation_id=...)`)?
3. **Component/schema names.** Bigger risk than operation IDs: if `PaymentV1Serializer` and `PaymentV2Serializer` both resolve to a component named `Payment`, they collide in a combined schema — and if V2 *inherits* V1, spectacular may name them confusingly. How does spectacular name components, and what's the hook to control it (`COMPONENT_SPLIT_*`, `get_component_name`, `@extend_schema_serializer(component_name=...)`)? Does inheritance confuse it?
4. **Serving.** Can one Django project serve several independent schema documents and several Swagger/Redoc UIs (one per version) cleanly? Show the URL wiring.
5. **Aliases.** If `/api/stable/` mounts the same router as `/api/v2/`, what does spectacular do — duplicate every operation, collide, or can it be told to skip the alias mount?
6. **Non-viewset views.** How much does spectacular infer for a bare `APIView` or `@api_view` function with no `serializer_class`? This determines the depth boundary for `diff`/`check` (see map: route composition works for anything, schema reasoning only for what spectacular understands).
7. **Schema diffing prior art.** Are there existing OpenAPI diff / breaking-change tools worth depending on rather than writing (`oasdiff`, `openapi-diff`, `openapi-changes`)? Note language, licence, maturity, and whether they're callable from Python.

Deliverable: a written report at `.scratch/apiver-mvp/research/03-spectacular.md` with working code sketches for the wiring, every claim cited, and an explicit list of things that are *not* supported or require private APIs.

## Context

- Settled: `diff` and `check` (0.2) diff **generated OpenAPI schemas**, not Python source. Item 7 above may make the CLI substantially cheaper.
- Settled: drf-spectacular is an acceptable hard dependency; it's the de-facto standard.

## Answer

Full report: [research/03-spectacular.md](../research/03-spectacular.md). Read against
drf-spectacular **0.30.0** (2026-07-06, BSD-3), which targets Django 2.2–6.0 / DRF 3.10–3.17 per
`tox.ini` (DRF 3.18 postdates it and is untested).

**Yes, cleanly — provided apiver emits one document per version rather than one combined document.**

1. **Per-version generation.** `SpectacularAPIView.as_view(urlconf=<list of URL patterns>)` is the
   supported, upstream-tested route (`views.py:58,66-77`; `tests/test_view.py:27-45`), with
   `custom_settings={...}` for per-version `TITLE`/`VERSION`/`SCHEMA_PATH_PREFIX` (FAQ-documented, but
   *not thread-safe*). `SERVE_URLCONF` is only the global default for that attribute — it cannot
   multiplex. `api_version` only filters views that set a DRF `versioning_class`, so it is a no-op for
   apiver's statically-prefixed version trees. Offline, `./manage.py spectacular --urlconf <module>`
   takes a module only (no `--patterns`).
2. **Operation IDs** come from the *path*, not the view (`openapi.py:451-491`). The same viewset at
   `/api/v1/` and `/api/v2/` gives `v1_payments_list` / `v2_payments_list` with no warning — unless
   `SCHEMA_PATH_PREFIX` swallows the version segment, in which case you get a warning plus positional
   `_2` suffixes (`plumbing.py:1239-1253`). Cleanest namespacing hooks: a custom
   `AutoSchema.get_operation_id()`, or a `POSTPROCESSING_HOOKS` entry (which runs *before* collision
   detection, so it prevents the suffixes). `@extend_schema(operation_id=...)` on a viewset *class* is
   explicitly rejected by upstream (`utils.py:529-536`).
3. **Component names** are `__class__.__name__` minus a trailing `Serializer`. **Inheritance itself is
   fine**: `PaymentV2Serializer(PaymentV1Serializer)` → `PaymentV2` / `PaymentV1`, both fully spelled
   out, no `allOf`, no collision. Two real traps: (a) two *different* classes with the *same* name
   (the natural outcome of a per-version layout, `v1/serializers.py` and `v2/serializers.py` both
   defining `PaymentSerializer`) produce a warning **and a silently wrong schema** — the second class
   is never mapped and V2's endpoints `$ref` V1's component (`plumbing.py:797-802` +
   `openapi.py:1696-1697`); (b) `@extend_schema_serializer` annotations live in a plain class
   attribute, so an **undecorated subclass inherits the parent's `component_name`** (and
   `exclude_fields`, etc.) and collides with it — verified by probe against verbatim
   `drainage.py:153-177`. Fix via `@extend_schema_serializer(component_name=...)` on every version, or
   better, one custom `AutoSchema.get_serializer_name()`.
4. **Serving.** Clean. UI views are already `@extend_schema(exclude=True)`; set
   `SERVE_INCLUDE_SCHEMA: False` and give each version its own `url_name`. Working wiring sketch in
   the report §5.
5. **Aliases.** If `/api/stable/` is in scope, spectacular **silently duplicates every operation**
   (dedup keys on `(path, method)`, not on callback) with distinct `stable_*` operationIds and no
   warning at all. Components are unaffected. The supported exclusions are the per-version `urlconf`
   list (right answer) or a `PREPROCESSING_HOOKS` filter; `@extend_schema(exclude=True)` cannot do it,
   because it is view-scoped and would drop the canonical mount too.
6. **Bare `APIView` / `@api_view`.** Route metadata stays fully correct (path, method, operationId,
   tags, auth, typed path params if the converter is typed); the payload degrades to a free-form 200
   object with an error + warning. So `diff`/`check` can reliably report **route-level** breakage for
   un-annotated APIViews and **nothing** about payloads — and should say so explicitly rather than
   report "no breaking changes".
7. **Diff prior art: use `oasdiff`.** Go, Apache-2.0, 1.3k stars, v1.28.0 (2026-08-06), ~505 checks,
   `ERR`/`WARN`/`INFO` severities, `--fail-on`, JSON output with a published JSON Schema — and it ships
   `--strip-prefix-base /api/v1 --strip-prefix-revision /api/v2`, which is literally `apiver diff v1 v2`.
   Not on PyPI; subprocess a static binary or Docker. **There is no maintained Python-native OpenAPI 3
   breaking-change library** (the only Python option, Yelp's `swagger-spec-compatibility`, is Swagger
   2.0-only and last released 2021). Optic was archived in Jan 2026.

**Two settings apiver must pin** or `diff` becomes unreliable: `SCHEMA_PATH_PREFIX` (the default
auto-estimator is `commonpath` over *the document's own paths*, so adding one endpoint can rename
every operationId in the file — `generators.py:210-220`), and the `COMPONENT_SPLIT_*` pair (flipping
them renames components).

Report §10 lists everything that needs private API (`self.path` inside a custom `AutoSchema`;
`drf_spectacular.plumbing`/`drainage` are internal) and everything unsupported outright (no alias
concept, no per-mount exclusion via the decorator, no inheritance relationship in the emitted schema,
no inheritance-safe `@extend_schema_serializer`).
