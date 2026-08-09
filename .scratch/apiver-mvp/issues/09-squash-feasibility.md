# 09 — Squash feasibility gate

Type: grilling
Status: resolved
Assignee: claude
Blocked by: 08

## Question

Squash is **mandatory** — it's the answer to the endless-chain problem and it was declared non-negotiable during charting. It ships at 1.0, not 0.1. This ticket is the gate that confirms the 0.1 decisions actually leave it reachable, *before* the 0.1 README promises it.

1. **Do the layout and manifest from [08](08-layout-and-manifest.md) give squash everything it needs?** Walk the squash algorithm against them step by step and find the missing input now, while the manifest schema is still cheap to change.

2. **Name what cannot be flattened.** The core problem: **`super()` across a version boundary.** If `PaymentV2ViewSet.get_queryset()` calls `super().get_queryset()`, severing the link to V1 means inlining V1's method body — and if that calls `super()` too, you're inlining DRF's. Same class of problem for:
   - `Meta` inner-class inheritance
   - decorated `@action` methods
   - class attributes assembled across the chain (`permission_classes`, `filter_backends`)
   - `**kwargs` passed up the MRO
   - multiple inheritance / mixins in the version chain

   Produce the explicit list of flattenable (declarative) vs. non-flattenable (behavioural) constructs.

3. **Confirm the best-effort contract.** Settled during charting: squash emits merged code, marks anything it can't prove safe with `# APIVER: manual review`, and produces a report — it does not claim correctness. A provably-correct squash would refuse to run on every real codebase, since every real viewset has a `super()` call. Confirm this is still the right call now that the non-flattenable list exists, and decide what fraction of markers makes the output useless rather than helpful.

4. **Output shape.** Generate a *new* directory (`api/v2_squashed/`) for review — never modify in place. Confirm, and decide what the developer does next (manual review then rename? a second `apiver squash --apply`?).

5. **LibCST vs `ast`.** Settle it. `ast` loses formatting and comments and isn't built for source-to-source transformation; LibCST preserves concrete syntax. Confirm LibCST, and check it can express the specific transformations item 2 requires.

6. **The alternative to squashing at all.** Rebasing rather than merging: declare a new **base version** (`V25 = BaseVersion(...)`) and archive V1–V24, so squash becomes an optimisation instead of a requirement. Does the manifest support this? Is it a cheaper answer to the endless-chain problem than source transformation? If it is, squash's priority drops even though it stays on the roadmap.

7. **Does 0.1's README promise squash?** Given it lands at 1.0, decide whether to advertise it as roadmap, mention it as a direction, or stay silent until it exists.

## Context

- Settled: squash is mandatory, best-effort, output to a new directory, 1.0.
- Settled: because `migrate` generates wiring rather than moving files, V1 may be scattered at squash time — squash reads V1's source *through the registry*, which points at exact classes. Confirm that indirection actually works.

## Answer

Recorded as [ADR 0004 — Squash feasibility](../../../docs/adr/0004-squash-feasibility.md). Glossary updated in [CONTEXT.md](../../../CONTEXT.md): added `Live` and `Archived` as lifecycle states, distinct from `Frozen` (mutability) and `Deprecated`/`Sunset` (service-lifecycle-while-live).

1. **No manifest schema change needed.** Squash reads live `Version` objects, not the manifest; the real per-registration question — does this override actually subclass its parent's registered class? — is checked via reflection (`__mro__`) at squash time, not stored anywhere. Where there's no subclassing, "squashing" is a directory move, not an inlining problem.
2. **Three-way flatten catalog**, replacing the ticket's flatter six-bullet list: mechanical splice (method/`Meta`/`@action`/`**kwargs` overrides — one technique, none of these are actually distinct problems), reflect-then-resynthesize (computed class attributes like `permission_classes` — LibCST can't evaluate expressions, so squash reads the resolved runtime value and emits fresh source), manual-review-only (in-chain multiple inheritance, and runtime-context-dependent logic like ticket 06's `del self.fields[...]` idiom).
3. **Best-effort contract confirmed. Per-registration reporting, no global marker-density threshold** — the sharpened catalog shows true non-flattenable cases are narrower than assumed at charting, so an aggregate percentage would obscure more than it tells a developer.
4. **No `--apply` flag, even at initial 1.0 ship.** Generates `api/v2_squashed/` plus a report and stops; promotion is a manual `git mv`.
5. **Rebasing is a complementary, already-available escape hatch, not a squash substitute, and needs zero new library support** — it trades old-version availability for shed implementation debt, which is a different trade than squash makes.
6. **LibCST confirmed via research** — feasible through `CSTTransformer` + `matchers` + `metadata` providers, but this is unprecedented, bespoke codemod work (no existing "flatten inheritance" tool found), not integration of an existing one. LibCST has no MRO engine, confirming that chain-boundary detection needs live registered classes, not syntax. Flagged explicitly so squash's eventual build ticket is sized as the hardest engineering in the roadmap, not routine integration.
7. **0.1's README names squash as a roadmap direction with an honest caveat** — paired with the rebasing workaround from item 5 — rather than a firm promise or silence. Answers the "doesn't this get unwieldy" objection central to the deltas-forward pitch without overclaiming an unproven feature.
8. **New: a `Live`/`Archived` guardrail, not just documentation, for the endless-chain worry.** A Version is Live while mounted (including Deprecated and Sunset — a Sunset Version still needs its mount to return 410); it becomes Archived only once unmounted. A Django system check — Warning level, reusing [ADR 0003](../../../docs/adr/0003-layout-and-manifest.md) item 9's mechanism — counts Live Versions off the live registry against a new setting `APIVER_MAX_LIVE_VERSIONS` (default 3), warning rather than blocking since nothing about serving breaks at 4 live versions. A project wanting a hard gate uses `manage.py check --fail-level WARNING`, no new apiver mechanism required.

**Feeds forward:** squash's own build ticket (post-0.1, still fog) inherits the three-way technique list and the novelty warning rather than an open-ended "figure out LibCST" task. [12 — Gating semantics](12-gating-semantics.md) needs to account for `Live`/`Archived` alongside `Deprecated`/`Sunset`, since a Sunset Version stays Live by this definition.
