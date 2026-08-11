---
status: accepted
---

# Squash is feasible but novel, best-effort by design, and paired with a live-version guardrail

Squash ships at 1.0, not 0.1, but was declared non-negotiable during charting — the answer to the
endless-chain problem inherent to a deltas-forward architecture. This is the gate that confirms it's
actually reachable given ADR 0001–0003, before anything promises it.

## Decision

1. **The manifest needs no schema change for squash.** Squash operates on the live `Version` objects
   (imported, like `migrate` already does), not the manifest alone — the manifest only needs to say which
   registrations exist and their `source_version`, which ADR 0003 already covers. The real per-registration
   question squash asks isn't in any schema: **does this override actually subclass its parent's
   registered class in Python?** Nothing in ADR 0002 requires that — an `override()` can be a fully
   independent class. That's checked via `__mro__`/`__bases__` reflection at squash time. Where there's no
   subclassing, squashing that registration is a directory move, not an inlining problem.

2. **What's flattenable splits three ways, not into one undifferentiated "hard" bucket:**
   - **Mechanical splice** (copy source text, stop recursing once a base class isn't part of apiver's own
     version chain): plain method `super()` overrides, `Meta` inner-class attribute inheritance,
     `@action`-decorated methods, `**kwargs` pass-through methods. One technique covers all of these —
     none of them are actually special cases of each other.
   - **Reflect, then resynthesize** (not literal copy): class attributes computed from a parent reference
     at class-body-eval time (`permission_classes = Parent.permission_classes + [Foo]`). LibCST can't
     evaluate that expression, so squash reads the *resolved* value off the live class and emits fresh
     literal source for it — a real technique, distinct from splicing, and it regenerates rather than
     preserves formatting for that attribute.
   - **Manual-review only, no attempt:** real multiple inheritance/mixins within the version chain (MRO
     correctness can't be mechanically guaranteed) and runtime-context-dependent logic like the
     `del self.fields[...]`-in-`__init__` idiom from ticket 06 (not resolvable by reflection at squash
     time, since it depends on `self.context`).

3. **Best-effort contract confirmed, with per-registration reporting instead of a global marker-density
   threshold.** Given the split above, true non-flattenable cases are narrower than assumed at charting —
   most real overrides are single-inheritance method/`Meta` cases, which are mechanically clean. The report
   flags individual registrations as clean or needs-review; there's no aggregate "% flagged" threshold
   that decides whether the tool is useful, since that number doesn't tell a developer what to actually
   look at.

4. **No `--apply` flag, even at initial 1.0 ship.** `apiver squash` generates `api/v2_squashed/` plus the
   report and stops. The developer reviews and promotes it with their own `git mv`. Auto-promotion is a
   destructive step layered on a tool that hasn't earned trust yet; it can be added later once squash has
   a track record.

5. **Rebasing (a fresh `Version("v25")` with no parent, archiving V1–V24) is a complementary escape hatch,
   not a substitute, and needs no new library support.** Nothing in the model requires exactly one Base
   Version forever — a developer can already stop deriving from the old chain today, using the same
   discovery flow ticket 02 covers for adopting apiver into an existing project. It doesn't reduce squash's
   priority: rebasing sheds implementation debt only by also dropping old-version *availability* (or
   duplicating maintenance by keeping V1–V24 as an unlinked codebase); squash is mandatory because it sheds
   implementation debt *while* old versions stay served.

6. **LibCST confirmed — but as unprecedented, bespoke codemod work, not tool integration.** The technique
   is `CSTTransformer` + `matchers` + `metadata.ParentNodeProvider`/`FullyQualifiedNameProvider`, manually
   rebuilding a class's statement sequence — LibCST's own `ApplyTypeAnnotationsVisitor` is the closest
   built-in precedent (same category: merging nodes from one CST into another), but no published codemod
   or tool does "flatten inheritance" as apiver would need it. LibCST has no MRO/C3-linearization engine,
   confirming item 2's split: distinguishing an apiver-chain base class from a third-party one needs the
   live registered classes, not syntax alone. This makes squash the hardest engineering in the roadmap
   despite shipping after 0.1 — worth sizing accordingly when a build ticket eventually takes it on.

7. **0.1's README names squash as a roadmap direction with an honest caveat, paired with today's
   workaround** — not a firm promise, not silence. Something like: long delta chains are the natural worry
   with a deltas-forward design, which is what `squash` (1.0) is for; today, the workaround is declaring a
   fresh base version and archiving the old one. Silence would leave the "doesn't this get unwieldy"
   objection — central to why deltas-forward was chosen over Cadwyn's inverse architecture — unanswered
   exactly where a skeptical reader would raise it. A firm promise would overclaim given item 6's finding
   that squash is novel, unproven engineering.

8. **A `Live`/`Archived` lifecycle guardrail, so the endless-chain worry has an actual mechanism, not just
   documentation.** A Version is **Live** while mounted in the URLconf — including while `Deprecated` or
   past `Sunset` (a Sunset Version still needs its mount to answer with 410). It becomes **Archived** only
   once its mount is removed; code may still exist on disk under the rebasing workflow from item 5, but it
   no longer counts. A Django system check, **Warning** level by default (same mechanism ADR 0003 item 9
   established for manifest staleness), counts Live Versions off the live `Version` registry — never the
   manifest, consistent with item 1's "code is authoritative" principle — against a new setting
   `APIVER_MAX_LIVE_VERSIONS` (default **3**). Warning, not a hard block: nothing about serving a request
   breaks at 4 live versions, so this is a maintenance-burden signal, not a correctness one. A project
   wanting a hard gate already has the tool: `manage.py check --fail-level WARNING` in CI — no new apiver
   mechanism needed for escalation.

## Considered options

- **A global marker-density threshold** ("if more than X% of the squash output is flagged, call the run a
  failure"). Rejected — an aggregate number doesn't tell a developer which registration to look at;
  per-registration flags do the same job better.
- **Shipping `--apply` at 1.0.** Rejected — squash is new and best-effort; auto-promoting on command adds
  a destructive step before the tool has earned trust. `git mv` keeps that step in the developer's
  explicit control.
- **Treating rebasing as a reason to deprioritize squash.** Rejected — rebasing and squash solve different
  problems (drop availability vs. keep it); rebasing is documented as a free complement, not a substitute.
- **Hard-erroring (not warning) when live-version count exceeds the max.** Rejected, mirroring ADR 0003
  item 9's reasoning: the check is advisory, since nothing about correctness depends on it; blocking
  `manage.py` commands over a maintenance-burden signal would enforce more than the check itself needs.
- **Counting Frozen Versions instead of mounted (Live) ones** for the guardrail. Rejected — `Frozen` is a
  mutability state unrelated to whether a Version is still being served; the actual maintenance cost comes
  from what's mounted, not what's immutable.
- **No built-in guardrail at all, documentation only.** Rejected — the whole point of this ticket is that
  the endless-chain problem needs an actual answer; a paragraph nobody reads isn't one.

## Consequences

Squash's build ticket (post-0.1, deferred fog) inherits a concrete technique list (splice / reflect-and-
resynthesize / manual-review) and an explicit novelty warning rather than an open-ended "figure out
LibCST" task. The `Live`/`Archived` distinction is now part of the domain model (`CONTEXT.md`) and will
need to be read by ticket 12's gating semantics work, since Sunset Versions stay Live by this definition.

**Amendment (ticket #41): item 8 stands as written — no exemption for Deprecated or Sunset Versions.**
Grilled while working #39: whether `APIVER_MAX_LIVE_VERSIONS` should free a slot once a Version is
Deprecated, or once it's past Sunset and answering 410, came up as a live alternative reading of the
guardrail. Two facts settle it against exemption in either form:

- **Sunset doesn't reduce the cost being counted.** `Version.urls` always calls `self._build()` and walks
  the full parent chain regardless of deprecated/sunset state — the sunset gate only short-circuits the
  per-request view with a 410, it doesn't skip import/instantiation. A Sunset Version carries the
  identical chain-build cost as a fully-Live one, so exempting it at Sunset would exempt it from a count
  that's still fully justified by the cost item 8 is pricing.
- **Deprecation doesn't stop the chain from growing.** `deprecate()` is independent of `freeze()` — a
  Version can be Deprecated and still accept `register()`/`override()`/`remove()` calls. Exempting at
  Deprecation would open exactly the hole item 8 exists to close: a developer could deprecate a version
  and keep piling deltas onto it indefinitely with zero guardrail pressure, the endless-chain scenario
  happening invisibly.

The only reading of "exempt" that isn't gameable is "exempt once Frozen" — but a Frozen, still-mounted
Version pays the identical build cost, so that's the "Counting Frozen Versions instead of mounted ones"
option already rejected above, just approached from the other direction. No state short of Archived
actually reduces the guardrail's cost basis. Closed as won't-fix: `APIVER_MAX_LIVE_VERSIONS` counts every
mounted Version regardless of lifecycle state, and squash / rebase-and-archive (item 5) remain the only
ways to free a slot.
