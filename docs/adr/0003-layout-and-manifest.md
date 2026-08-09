---
status: accepted
---

# Enforced layout for authored Versions, and the manifest as a generated, non-authoritative snapshot

The layout is what makes squash reachable; the manifest is what makes `apiver versions`, gating, and
squash possible at all. Both are coupled decisions about artifacts that live *outside* the running
process, so they're recorded together.

## Decision

### Layout

1. **Shape:** a flat per-version package — `api/v2/serializers.py`, `api/v2/views.py`,
   `api/v2/registry.py` (the file that performs that Version's `register()`/`override()`/`remove()`
   calls). No package-per-resource subpackaging; ticket 03's constraint (version-suffixed class names)
   already gets schema correctness without it, and this project doesn't need more structure than that
   yet.

2. **Two enforcement mechanisms, not one**, because they have different information available at
   different times:
   - **Class naming** (version-suffixed names, per ticket 03): enforced at `register()`/`override()`
     time — the call already holds the class object, so it checks `cls.__name__` against the Version's
     suffix and raises loudly on mismatch. No stack-frame introspection needed.
   - **Directory shape**: enforced via a Django system check — idiomatic, runs in `manage.py check`/CI,
     doesn't need to know what file called `register()`.

3. **Non-uniform layout is allowed across versions.** The Base Version may stay discovered-and-scattered
   while authored Versions are structured. `migrate` gives the base the *same* per-version package root
   (`api/v1/`) as authored versions, but writes only `registry.py` into it — the existing
   `serializers.py`/`views.py` never move. This gives every version a uniform root without forcing a
   special case into tooling that walks `api/<version>/`.

4. **The generated `registry.py` is a one-shot scaffold, not regenerated.** Hand-editable after
   `migrate` writes it once — like Django's own `startapp` boilerplate. Regenerating on every `migrate`
   run would clobber hand-added content, and there's no clean diff target to regenerate *from* short of
   the `--move` complexity already deferred to 0.3.

### Manifest

5. **Format and location:** standalone `apiver.toml` at the repo root. Not a Python module — the
   manifest is inert data, not live class references, and a Python module blurs the "code is
   authoritative, manifest is a snapshot" line ADR 0002 already drew. Not embedded in `pyproject.toml` —
   apiver rewrites this file programmatically, and that file is otherwise hand-curated and owned by
   other tools (poetry, ruff, mypy). Plain TOML is also parseable by tooling that never imports Django.

6. **Contents mirror the in-memory resolution table one-to-one, serialized** — no separate schema to
   design or keep in sync. Per version: parent, frozen status, deprecation/sunset dates (copied from the
   `Version` object at write time), and the resolution table (`{route_key: {action, source_version}}`).
   Plus top-level alias pointers (`{alias_name: target_version}`).

7. **Written by explicit CLI invocation only** — folded into `apiver migrate` for the base, a plain
   `apiver manifest` command otherwise. Never as an import-time side effect; writing files when a Django
   app is merely imported is fragile and breaks in read-only deploy environments.

8. **The running server never reads it.** Version gating and resolution at request time always compute
   from the live `Version` objects already in memory. `apiver.toml` exists only for consumers outside the
   running process: `apiver versions`, future `diff`/`check` (0.2), and squash (1.0). This narrows the
   ticket's original framing of four manifest consumers (migrate, `versions`, gating, squash) to three —
   gating was reclassified onto live objects, consistent with ADR 0002 item 5's "code is authoritative."

9. **Staleness is caught, not prevented, and at two layers.** `apiver manifest --check` regenerates the
   manifest in memory and diffs it against the committed file, exiting non-zero on any mismatch (missing
   file included) — the same idiom as Django's own `makemigrations --check --dry-run` for a
   generated-artifact-must-match-code problem. It's also registered as a Django system check at
   **Warning** level (reusing item 2's mechanism), so it fires on nearly every `manage.py` invocation, not
   only when a CI step remembers to run `--check`. Warning, not Error, because item 8 means a stale
   manifest doesn't break anything live — only offline tooling depends on it being current, so blocking
   `runserver` over it would enforce more than the check itself needs. Wiring `--check` into CI or a
   pre-commit hook is left to the consuming project.

## Considered options

- **Package-per-resource layout** (`api/v2/payments/{serializers.py,views.py}`). Rejected as structure
  the project doesn't need at 0.1 scale — flat per-version files already satisfy the schema-correctness
  constraint from ticket 03.
- **A single shared mechanism for both naming and layout enforcement.** Considered pairing both with
  either a system check or registration-time raise. Rejected: naming enforcement has exact information
  at `register()`-time with no introspection; layout enforcement doesn't, and forcing it through the same
  moment would mean walking the caller's stack frame to find the file, which is fragile compared to a
  system check that just looks at what's on disk.
- **Regenerating `registry.py` on every `migrate` run.** Rejected — no clean diff target once
  hand-edited, and re-deriving it from the URLconf every time is the `--move` problem already deferred.
- **Manifest as a Python module holding live class references.** Rejected — would make the manifest
  *code*, not a snapshot, contradicting item 8 and ADR 0002 item 5.
- **Manifest embedded in `pyproject.toml`.** Rejected — apiver's automated rewrites would collide with a
  file conventionally hand-edited and owned by other tooling.
- **Version gating reads the manifest at request time**, as the ticket originally assumed. Rejected in
  favor of reading live `Version` objects — the manifest would then be a second source of truth that
  could silently disagree with code, exactly what ADR 0002 item 5 ruled out.
- **`apiver manifest --check` as an Error-level system check**, blocking `runserver`/`test` outright.
  Rejected — the running server doesn't consult the manifest, so blocking on its staleness would enforce
  a correctness guarantee the check itself doesn't need; a Warning gives the same visibility without the
  false blocker.

## Consequences

Squash (ticket 09) inherits two concrete facts to verify: it must read the Base Version's source
*through* `api/v1/registry.py`'s pointers rather than assuming a flat scattered layout, and it can rely
on the manifest's resolution table being a faithful, current snapshot **only** immediately after a
`manifest --check` passes — never as an unconditional given.
