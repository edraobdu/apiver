---
status: accepted
---

# Squash flattens `registry.py` only — no LibCST, whole ancestor chain, auto-applied

Ticket #77 pulled squash into 0.1 (previously slated as the headline 1.0 feature, per ADR 0004 and the
README's own roadmap caveat). Scoping the actual build surfaced that ADR 0004's premise — squash as an
LibCST codemod flattening a View class's Python inheritance — assumed implementation code lives inside a
version's root directory. ADR 0003 (ticket #73 amendment) already established the opposite: a version's
root only ever *had* to contain `registry.py`, with serializers/views discovered from wherever the project
already keeps them. Grilled directly while scoping this ticket: if that's true, squash never had a class
body to flatten in the first place. This ADR supersedes ADR 0004's mechanism (item 6 and the connected
parts of items 1–4) while keeping its guardrail (item 8, `APIVER_MAX_LIVE_VERSIONS`) untouched.

## Decision

1. **Squash operates on `registry.py` files only, never on a View or Serializer's source.** Paired with
   ADR 0003's ticket #77 amendment (this same ticket) making that hard — a version's root may contain only
   `registry.py`, which may contain only imports, its `Version(...)`/`.derive()` line, and
   `register()`/`override()`/`remove()` calls — squashing away a version can never delete code a surviving
   version still needs. Implementation code was never inside the directory being deleted, by construction,
   not by squash reasoning about it. This is what makes items 2–5 below possible without any LibCST,
   `__mro__` reflection, or splice/reflect/manual-review split: there is no class body to reason about.

2. **`apiver squash TARGET` takes one version, not a pair, and absorbs its entire ancestor chain.**
   `apiver squash v4` walks `v4.parent`, `.parent.parent`, … back to the earliest ancestor and flattens
   all of it into `v4`. A pairwise `squash v1 v2` was considered and rejected — a partial squash just
   leaves a shorter chain still needing squashing later, with no case where stopping partway is the actual
   goal.

3. **Preflight validates every absorbed version, all at once, before writing anything.** Even with item 1
   as a system-check-enforced rule (checked whenever `manage.py check` runs), squash re-validates at run
   time rather than trusting that the check already ran and passed — the two are independent enforcement
   moments for the same rule, exactly as ADR 0003 item 2 already splits class-naming (`register()`-time)
   from directory-shape (system check) enforcement. Every violation across every absorbed version is
   collected and reported together, mirroring `apiver init`'s existing "fail closed, list everything"
   posture (ADR 0003 item 1's ticket #02 lineage) — not fix-one-rerun-fix-next. Any violation refuses the
   entire squash; nothing is written.

4. **The target version's `registry.py` is fully regenerated, not appended to** — every key in
   `target.resolution_table` becomes a plain `register()` call, in deterministic (sorted-by-key) order, and
   the target's own `Version(...)`/`.derive()` line drops its parent: after squash, the target is a new
   Base Version in every sense apiver's model recognizes (no parent, exempt from the `_check_suffix`
   version-suffix requirement, same as any Base Version). `override()`/`remove()` calls have nothing left
   to mean once nothing is inherited, so they don't appear in squashed output. This is a deliberate
   departure from ADR 0003 item 4's "one-shot scaffold, never regenerated" posture for `mount`/`init` —
   that posture protects hand-edits from being clobbered by an unrelated later command; squash's entire
   purpose *is* regenerating a version's registry as standalone source, so regenerating it is the feature,
   not a violation of it. A developer's hand-added comments in the target's pre-squash `registry.py` don't
   survive — an accepted, visible-in-the-diff cost of running squash, not a silent one.

5. **Auto-applied to the target's `registry.py` — no staging directory, no `--apply` flag, no manual
   `git mv`. Squash never deletes anything.** ADR 0004 item 4's caution (stage output + report, developer
   promotes by hand) was sized for a codemod editing view class bodies, where a wrong splice is a subtle
   correctness bug easy to miss in review. A `registry.py` regeneration from the already-composed,
   already-tested `resolution_table` has a much smaller failure surface, and `git diff` on the rewritten
   file is a complete, standard review surface a developer already knows how to use — so the rewrite itself
   is auto-applied, in place, no separate promotion step. But squash's job ends there: the absorbed
   versions' directories are left exactly as they are. Once nothing imports them (item 7), they're inert,
   safe to delete — but deleting them, unmounting them from the Aggregation Root, and dropping them from
   `APIVER_VERSIONS` is a distinct, separate operation (removing a version, not flattening one) with its
   own blast radius apart from what squash needs to reason about. That's `apiver remove`'s job, tracked as
   its own future ticket, not this one's.

6. **Schema and docs registrations are regenerated as `schema_view()`/`docs_view()` calls, not import
   statements**, keyed on the literal `"schema/"`/`"docs/"` convention `apiver mount`'s own generator
   (`render_mount_registry`) already hardcodes — not a new detection mechanism. Every other registration's
   handler is resolved to an importable `(module, symbol)` pair the same way `apiver init`'s
   `_resolve_class_symbol`/`_resolve_function_symbol` already do (including their identity-verification
   against a fresh import), reused rather than reimplemented.

7. **Downstream versions (a `v5` derived from the squashed `v4`) need no changes at all.** `override()`/
   `remove()` validity only depends on a key being resolvable through the parent chain, never on which
   version originally sourced it (`version.py`'s `_resolved_keys()`) — squashed `v4` resolves the identical
   key set as before, now locally instead of inherited. Combined with item 1, this also means a downstream
   version can never have been depending on an absorbed version's directory contents in the first place, so
   there is nothing for squash to fix up there either.

8. **Item 8 of ADR 0004 (the `Live`/`Archived` guardrail, `APIVER_MAX_LIVE_VERSIONS`) is unaffected and
   stays in force as written**, including its ticket #41 amendment. Squash is one of the two ways
   (alongside rebasing) to bring a project back under the guardrail; nothing about how the guardrail itself
   counts or warns changes.

## Considered options

- **File-level merge of `views.py`/`serializers.py`** (an earlier framing during scoping): copy an
  absorbed version's directory wholesale and merge same-named files, stripping now-redundant cross-version
  imports. Rejected once item 1 became a hard rule — there is nothing to merge when implementation code was
  never inside the version directory to begin with; the whole class of collision (two files defining the
  same name) that this approach had to handle disappears with it.
- **LibCST class-body splicing** (ADR 0004's original mechanism): mechanical splice / reflect-and-
  resynthesize / manual-review-only, keyed on `__mro__`/`__bases__` reflection. Superseded — built on the
  premise that a version's root holds implementation code, which ADR 0003 (ticket #73 amendment) had
  already ruled out before this ticket was scoped.
- **Soft convention, README-only** (item 1's alternative — leave ADR 0003's ticket #73 "not mechanically
  enforced" position as-is, let squash flag inline definitions as best-effort needs-review). Rejected: a
  soft convention can't guarantee deleting a directory is safe, which is squash's entire premise. See ADR
  0003's ticket #77 amendment for the full reasoning.
- **Staged output + manual `git mv`** (ADR 0004 item 4, carried forward as a default). Rejected for this
  narrower mechanism — see item 5.
- **Pairwise `squash OLD NEW`.** Rejected — see item 2.
- **Squash also deletes the absorbed versions' directories.** Considered, since item 7 establishes doing so
  is always safe. Rejected — deletion also means unmounting from the Aggregation Root and dropping the
  entry from `APIVER_VERSIONS`, which is a different operation (removing a version) with its own concerns
  squash's own scope (flattening a chain into one target) doesn't need to take on. Left to a future `apiver
  remove` ticket.
- **Appending to the target's existing `registry.py` instead of full regeneration** (preserve keys the
  target already had verbatim, only add `register()` calls for newly-absorbed keys). Rejected — the target
  itself may still hold `override()`/`remove()` calls against a parent that's about to stop existing, which
  would need surgical rewriting anyway; full regeneration from the already-correct `resolution_table` is
  simpler and strictly more reliable than partially rewriting hand-authored source in place.

## Consequences

`check_version_layout` (ADR 0003 item 2's directory-shape mechanism) gains the two new checks ADR 0003's
ticket #77 amendment specifies; squash's own preflight validation reuses the same detection logic rather
than duplicating it. `apiver init`'s `_resolve_class_symbol`/`_resolve_function_symbol` and
`render_mount_registry`'s schema/docs convention are both reused by squash's registry generation instead of
being reimplemented.

Ticket #57 (a possible Version-wide config layer) remains an open, undecided ticket. If it ever lands as
something other than real per-endpoint `override()` calls (e.g. a shared mixin or middleware apiver
injects), squash — like everything else in this ADR — only ever reasons about what `register()`/
`override()`/`remove()` actually declared, so it would need revisiting then. Nothing here narrows that
future ticket's options.

**Amendment (PR #83 review): items 4–5 corrected — squash keeps the target's parent chain intact; it
never makes the target a new Base Version.** As originally written, item 4 had squash strip the target's
`.derive()` line and re-emit every key as `register()`, becoming a fresh, parentless Base Version. That's
wrong: it silently discarded the parent link a developer never asked to discard, and — caught by the CLI
round-trip test that reimports the freshly-written file in a fresh process — it isn't even the version
`apiver remove` (item 5) needs squash to produce, since *that* command is what's supposed to be the one
cutting the parent link, not squash.

- **The parent-derivation line is preserved as-is** (`{target} = {parent}.derive({target!r})`), and every
  key already resolvable through `target.parent` (`parent._resolved_keys()`) is re-declared with
  `override()`, never `register()` — the parent still resolves it, and `register()` raises on a key that
  already exists. Only a key `target` genuinely introduces itself, with no ancestor ever having had it,
  uses `register()`. A key the parent still resolves but `target.resolution_table` doesn't (something in
  the chain removed it) needs an explicit `remove()` re-declared too — full regeneration otherwise drops
  the original `.remove()` call silently, resurrecting the parent's route in the freshly-written file.
- **This surfaced a real conflict with `_check_suffix`** (`version.py`, ADR 0003 item 2): `override()`
  refuses a handler whose class name doesn't carry the *overriding* version's own suffix, and a squash-
  flattened key's handler was authored for whichever version originally introduced it, not the target —
  `RefundViewSetV2` re-declared via `v3.override(...)` doesn't carry `v3`'s suffix. Resolved with a
  narrow, targeted exemption on `override()` (`Version._current_handler_for`): the check is skipped only
  when the handler passed is the *exact same object* already resolving at that key. This is safe because
  the collision `_check_suffix` exists to catch — a genuinely new or different class silently colliding
  under a reused name — can't happen here: that object was already part of the target's own composed
  schema, under that exact name, before the call (drf-spectacular's schema generation is already scoped
  to each version's own mounted patterns, so there's no cross-version leakage to worry about either). A
  genuinely different, non-suffixed handler still raises, unchanged.
- **Item 5's "once nothing imports them, they're inert, safe to delete" is wrong** for the same reason —
  the absorbed versions are still imported, still live, still exactly as load-bearing as before squash
  ran. Squash's own CLI output no longer implies otherwise; deleting anything is entirely `apiver remove`'s
  job, once it exists, not something a developer should be nudged to do by hand in the meantime.
- **Item 7 stands, more precisely true than originally reasoned**: downstream versions need no changes
  specifically *because* the parent chain is untouched — there was never a chain-restructuring step for
  them to be affected by in the first place.
