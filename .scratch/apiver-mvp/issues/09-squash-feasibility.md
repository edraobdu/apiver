# 09 — Squash feasibility gate

Type: grilling
Status: open
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
