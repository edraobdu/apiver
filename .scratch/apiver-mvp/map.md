# Map: apiver 0.1

## Destination

`apiver` 0.1 published on PyPI — delta-based API versioning for Django REST Framework, where V2 is defined as a set of overrides on V1 and the router composes a *complete* V2 API surface, resolving unchanged routes back to V1's implementation.

Shipped alongside it: a **reference DRF project** enumerating every change-shape the library claims to support. If a change-shape isn't in that project, the library doesn't support it.

## Notes

**Domain:** Python library. Django REST Framework first. Packaged and published to PyPI.

**This map carries execution.** The destination is a shipped release, not a spec, so build tickets are in scope — but they stay in the fog until the decisions in front of them are settled. Don't ticket "implement the router" before the route identity model exists.

**Skills every session should consult:** `/grilling` and `/domain-modeling` by default. `/prototype` for prototype tickets. `/research` (subagent) for research tickets. `/tdd` once build tickets graduate.

**Standing decisions for this effort** (settled in the charting session, don't relitigate without cause):

- **Deltas forward.** V(n) inherits V(n-1). Newest code sits at the bottom of the inheritance stack; this is accepted consciously, not by default. The inverse (Stripe-style, latest-canonical + backward transforms) is the road not taken — it is what Cadwyn does, and staying off it is the differentiator.
- **DRF-only internals, framework-neutral public vocabulary.** No `apiver.core` abstraction layer until a second adapter exists to justify one. Keep the *names* portable (`Version`, `derive`, `override`, `remove`), not the *layer*.
- **Path-keyed resolution, not resource-keyed.** A registered viewset *expands into* several path entries. APIViews, function views and plain Django views are first-class routes, not second-class citizens.
- **Route composition works for anything; schema reasoning works only for what drf-spectacular understands.** A feature-depth boundary, documented honestly — not a discovery boundary.
- **Layout is enforced for versions you author, discovered for the base.** The existing scattered V1 stays where it is; `apiver migrate` generates wiring, never moves files.
- **Build it for yourself first.** Four DRF versioning libraries flatlined over a decade (see research/01-prior-art.md). PyPI is a side effect, not the goal. This has to be worth running on your own APIs even if nobody else adopts it.

**0.1 scope:** version model · path-keyed resolution · composing router · route + field removal · enforced layout for authored versions · version manifest · aliases (stable/latest/testing) · deprecation + sunset + unknown-version gating · drf-spectacular correctness · CLI with `apiver migrate` and `apiver versions`.

**Deferred:** `diff` / `check` (0.2) · `migrate --move` (0.3) · `squash` (1.0) · FastAPI adapter (post-1.0).

## Decisions so far

<!-- one line per closed ticket: gist + link -->

- [Prior art: is there a gap?](research/01-prior-art.md) — yes, technically: DRF's built-in versioning only sets `request.version`, with no fallback; no DRF library does delta/inheritance composition. Cadwyn is FastAPI-only and takes the *inverse* architecture. But four DRF versioning attempts flatlined over a decade, so demand is the weak point, not feasibility. `apiver` is free on PyPI.
- [URLconf walk: what is actually recoverable?](issues/02-urlconf-walk-feasibility.md) — `migrate` is feasible. Every DRF callable carries `.cls`/`.initkwargs`; `basename` and `detail` are ground truth in `initkwargs`, so the router object is never needed. Do **not** reuse drf-spectacular's `EndpointEnumerator` (it silently drops non-`APIView` routes). 16 failure modes catalogued; `.cls` is undocumented, so pin a version matrix and CI-test it.
- [drf-spectacular: per-version schemas](issues/03-spectacular-integration.md) — per-version documents are near-free and upstream-tested; combined documents are where collisions live. Component names come from the class name, so **two same-named serializer classes in different version modules silently emit a wrong schema** — version-suffixed class names are load-bearing, not style. Alias mounts silently duplicate every operation. `SCHEMA_PATH_PREFIX` must be pinned per version or `diff` is built on sand. `oasdiff` already implements `apiver diff` almost exactly.
- [Route identity: what is the unit of override?](issues/01-route-identity.md) — resolution table keyed by **absolute path**, each entry carrying a `RouteIdentity` read from `initkwargs`; a **whole registration** is the smallest unit of override or removal; base version keeps bare URL names while authored versions get Django instance namespaces; nested/custom routers refused in 0.1, with a mandatory self-verifying re-walk. Recorded as [ADR 0001](../../docs/adr/0001-route-identity.md), glossary in [CONTEXT.md](../../CONTEXT.md).
- [The change-shape catalogue](issues/04-change-shape-catalogue.md) — 22 change-shapes classified clean/awkward/unsupported with diff-visibility tracked as a separate axis; the honest 20% clusters in subtraction (field/action removal and rename, resolving through ticket 06) and diff blind spots (`SerializerMethodField` output, permissions, pagination, filtering, default ordering, error shape, throttling — trivial to write, invisible to schema-diff).
- [Prove the mechanism (the weekend spike)](issues/05-prove-the-mechanism.md) — mechanism survives contact with real Django/DRF, all 17 spike tests pass (7 verification items + 50-endpoint acceptance test + 2 regression tests). Two unpredicted findings: composition must use `SimpleRouter` not `DefaultRouter` (flagged on [07](issues/07-public-api-surface.md)); route ordering (explicit views before router urls) is load-bearing, not stylistic. Bare `APIView`s route correctly but degrade in the schema, confirming the standing "route composition works for anything, schema reasoning doesn't" decision. Spike code on branch `prototype/05-mechanism-spike`.
- [Field removal: the idiom, and whether a helper earns its place](issues/06-field-removal.md) — canonical idiom is `Meta.fields` surgery (schema-correct, verified), no helper; `field = None` is a silent footgun apiver must guard against loudly, while `action = None` correctly removes an inherited `@action` and is documented as-is; recommended default workflow is deprecate-then-remove — soften in V(n) (`required=False` / drf-spectacular's native `deprecate_fields`), hard-remove in V(n+1) — with no phase-out marker in 0.1, deferred to `check` (0.2).

## Not yet specified

- **0.1 build slices.** The actual implementation tickets. Wait on 07, 08 — and the reference project specifically waits on [11 — Reference project: shape and structure](issues/11-reference-project-shape.md) as well.
- **Alias and gating semantics in detail.** How `stable`/`latest`/`testing` are declared and mounted; exact `Deprecation`/`Sunset` header formats; whether aliases appear in the schema. Downstream of the manifest schema (08). **Now known to be harder than assumed:** "just mount the router twice" (proposed in the original Gemini and ChatGPT threads) makes drf-spectacular *silently* duplicate every operation, because its dedup keys on `(path, method)` rather than on the callback. Also open: does an alias mount get its own URL namespace, or reuse the target version's?
- **Intra-version hyperlinking.** What a V2 `HyperlinkedIdentityField` (or any `reverse()` inside a versioned view) should resolve to. Route identity settled that authored versions are namespaced, which means a view inherited from V1 into V2 will `reverse()` into V1 unless something makes it version-aware. May need library support; may be documented as the developer's problem. Surfaced by [Route identity](issues/01-route-identity.md).
- **DRF/Django/spectacular support matrix and contract tests.** apiver depends on undocumented DRF attributes (`callback.cls`, `.initkwargs`, `.actions`). Needs a pinned supported range plus CI assertions so a DRF upgrade fails loudly in apiver rather than silently in a user's project.
- **Docs and README.** Including the positioning line and the first example (must be greenfield, given enforced layout for authored versions).
- **CI, packaging, release process.** Python/Django/DRF support matrix.
- **"Adopting apiver in an existing project"** — its own documented chapter, non-trivial. Downstream of `migrate`'s final shape.
- **APIView schema depth.** Plenty of DRF codebases are mostly `APIView`. Routing them is settled; how much `diff`/`check` can say about them is not. Revisit at 0.2.

## Out of scope

- **Model / database-layer drift.** A dropped column or a nullable going non-null breaks V1 regardless of what the serializer layer does. apiver versions the API surface only. Document loudly; flag as a possible future direction, not a 0.1 concern. Scope creep here turns the project into an ORM.
- **Stripe-style backward transforms.** The inverse architecture. Deliberately not taken — see Standing decisions.
- **FastAPI / Quart / Litestar adapters.** Post-1.0 at the earliest, and only once the abstraction has survived contact with a real second framework.
- **`apiver migrate --move`** (physically relocating and rewriting imports of the existing scattered API). Considered and rejected for 0.1 in favour of generate-wiring-only: a viewset drags serializers, mixins, permissions and utils with no clean cut line, and imports invisible to the URLconf (settings strings, Celery paths, admin, tests) would silently break. Revisit as an opt-in 0.3 step *after* generate-only has proven the wiring correct.
