---
status: accepted
---

# Enforced layout for authored Versions, and the manifest as a generated, non-authoritative snapshot

The layout is what makes squash reachable; the manifest is what makes `apiver versions`, gating, and
squash possible at all. Both are coupled decisions about artifacts that live *outside* the running
process, so they're recorded together.

## Decision

### Layout

1. **Shape:** a version's root is a package containing `api/v2/registry.py` (the file that performs
   that Version's `register()`/`override()`/`remove()` calls) — the one file every Version, Base or
   Authored, is required to have. Nothing else about the root's contents is required or forbidden; a
   Version's serializers, views, and any other implementation code live wherever the developer's project
   already organizes them, discovered by `registry.py`'s imports rather than relocated into the version
   root. *(Updated by the ticket #73 amendment below — see there for what this replaced and why.)*

2. **Two enforcement mechanisms, not one**, because they have different information available at
   different times:
   - **Class naming** (version-suffixed names, per ticket 03): enforced at `register()`/`override()`
     time — the call already holds the class object, so it checks `cls.__name__` against the Version's
     suffix and raises loudly on mismatch. No stack-frame introspection needed.
   - **Directory shape**: enforced via a Django system check — idiomatic, runs in `manage.py check`/CI,
     doesn't need to know what file called `register()`. Now checks a single thing for every Version,
     Base or Authored alike: does `registry.py` exist.

3. **Layout is uniform across every version, Base and Authored alike.** Every version gets the same
   per-version package root (`api/v1/`, `api/v2/`, ...) with `registry.py` written into it — the
   existing `serializers.py`/`views.py`, and any code an Authored Version's overrides need, never move
   there. This is the Base Version's original treatment (item 3 as first written) extended to every
   version rather than left as its exception; see the ticket #73 amendment below for why the asymmetry
   didn't hold up.

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

Squash (ticket 09) inherits two concrete facts to verify: it must read every version's source *through*
its `registry.py`'s pointers rather than assuming a flat, generated-in-place layout, and it can rely on
the manifest's resolution table being a faithful, current snapshot **only** immediately after a
`manifest --check` passes — never as an unconditional given.

**Amendment (ticket #73): items 1–3 rewritten — `serializers.py`/`views.py` are no longer required, or
even expected, inside an Authored Version's root; only `registry.py` is.** As originally written, the
Base Version got the "discovered, not relocated" treatment (item 3) but Authored Versions didn't — a
freshly-`mount`ed Authored Version had to have hand-created `serializers.py`/`views.py` files to pass
`apiver.E002`, a requirement the README's own quickstart never followed (it inlines override classes
directly in `registry.py` instead).

Grilled directly: apiver's job is to enforce *where routing is declared*, not *where implementation code
lives* — a project adopting apiver already has a working structure for serializers and views, and
forcing a second one just for versions it authors later contradicts the same "don't move a file"
promise item 3 already made for the base. The asymmetry wasn't a deliberate trade-off surfacing two
different needs; it was an oversight from generalizing the base's exemption only as far as the ticket
in front of it required. Extending it fully removes the asymmetry rather than justifying it.

Consequence for squash: none. Item 1's finding above already generalizes cleanly — squash was always
going to read source through live class reflection (`__mro__`, module introspection via
`inspect`/`__module__`), never a hardcoded path, because that's the only way it already worked for the
Base Version's scattered layout. Authored Versions now get the identical treatment, not a new one.

`registry.py`'s role sharpens as a consequence: it's the one artifact every version is guaranteed to
have, so it becomes the de facto index of a version's whole registration surface — every
`register()`/`override()`/`remove()` call in one file, everything else imported. Not mechanically
enforced (nothing stops a developer from defining a class inline there), but it's the convention the
README now models throughout.

**Amendment (ticket #77): the ticket #73 amendment's "not mechanically enforced" is reversed — a
version's root may now contain *only* `registry.py` (plus `__init__.py`), and `registry.py` itself may
contain only imports, its `Version(...)`/`.derive()` line, and `register()`/`override()`/`remove()`
calls. A class or function defined inline there, or any other file dropped into the version's root, is
now an `apiver check` **Error**, not a silent option.**

Surfaced while scoping squash (ticket #77, ADR 0009): squash's whole mechanism — deleting an absorbed
version's directory once its routes are folded into the survivor — is only safe if nothing a *surviving*
version still needs can possibly live inside the directory being deleted. Under the ticket #73 amendment,
it could: the README's own inline-override pattern put a class directly in `registry.py`, and nothing
stopped a class in one version's `registry.py` from being imported (or subclassed) by a later version's.
Squash has no way to know, short of parsing every version's source for cross-version references, whether
deleting `v1/` would silently break `v2/`. Rather than build that detection, the ticket #73 amendment's
premise — "nothing stops a developer from defining a class inline there" — is the thing that no longer
holds: forbidding it outright removes the ambiguity squash would otherwise have to reason about, and
removes it at the one moment that actually matters (before a version is ever authored), not after.

This still keeps item 3's core finding: apiver enforces *where routing is declared*, never *where the
rest of a project's code lives*. Serializers, views, and everything else stay wherever the project already
organizes them, discovered by `registry.py`'s imports — that part of the ticket #73 amendment is
unchanged. What's reversed is narrower: `registry.py` itself, and the version's root directory around it,
are now apiver's exclusively, the same way the Aggregation Root already is.

This is also why `APIVER_ROOT_DIR` gets a real default, `"apiversions"`, instead of requiring explicit
configuration as before: the overwhelmingly common convention for a hand-rolled Django REST project is to
call its app `api/`, with serializers/views/etc. living directly inside it. A hard "nothing but
`registry.py` lives here" rule collides head-on with that convention if apiver's own root directory is
*also* conventionally named `api/` — a developer adopting apiver would either have to rename their
existing app (exactly the "moving a file" cost ADR 0003 item 3 already promised against) or fight the new
restriction. `apiversions` is deliberately not a name any pre-existing Django app is likely to already
have. `apiver init` still warns (non-fatal — the same advisory posture as the manifest-staleness and
max-live-versions checks) if the resolved root directory already exists on disk before `init` would
create it fresh, since that's the one moment a pre-existing, unrelated directory of the same name would
otherwise collide silently. A project that wants a different name still sets `APIVER_ROOT_DIR` explicitly
— this is a default, not a new required-fixed value.

Consequence for the README: its quickstart already keeps `ProductSerializerV2`/`ProductViewSetV2` outside
`registry.py` (imported from `products.views`, not inlined), so the walkthrough itself doesn't change —
only the settings snippet's `APIVER_ROOT_DIR` value and an explicit callout of the new hard rule.
