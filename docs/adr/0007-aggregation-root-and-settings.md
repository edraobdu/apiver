---
status: accepted
---

# A generated aggregation root for mounting versions, and settings consolidated around it

Adoption into an already-versioned project surfaced a real gap while building #22: `apiver migrate`
had no way to keep a project's true root `urls.py` untouched as later versions get authored, and the
three settings that existed to support adoption (`APIVER_BASE_VERSION`, `APIVER_VERSION_ROOTS`,
`APIVER_VERSIONS`) had grown redundant with each other without anyone deciding they should be.
Decided in #39.

## Decision

1. **No auto-detection of pre-existing version-shaped paths.** `migrate` continues to require
   `APIVER_BASE_VERSION` explicitly; nothing scans the target project for `/v1/`, `/v2/`-shaped paths to
   default a new base version past. The developer already knows their own project's shape — heuristics
   here would be guesswork dressed up as a feature, wrong at the one moment (adoption) where being wrong
   is expensive.

2. **A generated, hand-maintained aggregation root.** `migrate` — and, from 0.1 on, a greenfield project
   too — generates one file, `<root package>/urls.py`, composing every Live version's mount at its full
   absolute path: `path("api/v1/", include(v1.urls))`. The project's actual root `urls.py` includes it
   once, at an empty prefix — `path("", include(api.urls))` — and is never touched again for a version's
   sake. This is the entire adoption/authoring footprint on the one file every project already owns for
   reasons that have nothing to do with apiver (admin/, health checks, third-party auth urls).

3. **Two settings replace the overloaded `--prefix`:** `APIVER_ROOT_DIR` (the dotted path to the
   aggregation package on disk, e.g. `"api"`) and `APIVER_ROOT_PREFIX` (the absolute URL path every
   version mounts under, e.g. `"api/"`). Filesystem location and URL path are distinct facts — routing
   structure need not mirror package structure even though it usually does — and conflating them under
   one flag was exactly what made "root" ambiguous while designing this.

4. **`APIVER_VERSION_ROOTS` is removed.** Every version's package is derived as
   `f"{APIVER_ROOT_DIR}.{name}"` — a version's directory is always named after the version, directly
   under the root. This turns ADR 0003 item 1's flat-layout rule from a convention independently declared
   per version into a structural fact: a mis-named directory isn't flagged, it's invisible, because
   nothing ever derives a path to it.

5. **`APIVER_VERSIONS` narrows from `{name: dotted_path}` to a plain list of Live names**, e.g.
   `["v1", "v2"]`. Live-ness (mounted in the URLconf) stays something only a developer can state — a
   directory walk can't distinguish a Live version from an Archived one whose code is deliberately still
   on disk (ADR 0004 item 8) — but the dotted path to each version's `Version` instance is now derived by
   item 4's same convention (`f"{APIVER_ROOT_DIR}.{name}.registry.{name}"`), so a version is typed once,
   as a name, not twice as a path.

6. **`Version.schema_view()` keeps its existing signature.** No `root=`/`prefix=` split. `APIVER_ROOT_PREFIX`
   centralizes the string every call site needs: whatever writes a `schema_view(prefix=...)` call —
   `migrate`'s generated code for the base version, or a hand-written line in an authored version's
   `registry.py` — computes it as `APIVER_ROOT_PREFIX + f"{name}/"` instead of typing an absolute path
   from scratch. Closes ticket #10 / #39's decision-point 3 without reopening ADR 0002's public surface.

7. **A new CLI command mounts an authored version into the aggregation root** (name and full mechanics
   left to the follow-up build ticket). `migrate` keeps owning the base version's initial mount — it
   already discovers and writes wiring for the base version, so this is unchanged responsibility, not a
   new one. Neither this command nor `migrate` writes to `settings.py`: adding a version's name to
   `APIVER_VERSIONS` stays a hand-edit, consistent with `migrate` today only ever reading settings, never
   writing them — `settings.py` can hold arbitrary project-specific structure apiver doesn't own.

## Considered options

- **Auto-detecting pre-existing version-shaped paths** to default the base version past them (item 1).
  Rejected — which pattern even counts as "version-shaped" (`/v1/`? `/api-v1/`? `/version1/`?) is a guess,
  and adoption is the one moment where a wrong guess is expensive.
- **A relative aggregation file**, portable and reusable at any mount point, with the true root repeating
  the absolute prefix (`path("api/", include(api.urls))`). Rejected in favor of the absolute-path design
  in item 2 — it removes the one remaining piece of duplicated knowledge between the file apiver
  generates and the file the developer owns.
- **Deriving `APIVER_VERSIONS`'s Live-ness from the aggregation root's actual `include()`s** (introspecting
  Django's resolved URLconf) instead of a hand-maintained list. Rejected for 0.1 — nothing today recovers
  which `Version` object built a given resolved mount; that machinery would be new and speculative next
  to a one-line hand-edit that already matches how mounting itself is a developer action.
- **Reading Live-ness off `Version.deprecated`.** Rejected — `Version` carries no "mounted" attribute at
  all (`src/apiver/drf/version.py:137-146`), and the two facts are independent: a Deprecated version is
  still very much Live (ADR 0004 item 8), and an unmounted `Version` object can still exist fully composed
  in memory (ADR 0002's beta-version case).
- **Keeping `APIVER_VERSION_ROOTS` explicit alongside the new settings**, for projects where a version's
  package might live somewhere irregular. Rejected — nothing in the codebase has ever needed that
  flexibility, and it's exactly the kind of scattered-by-default shape this ADR exists to close off.
- **A separate `apiver init` command to scaffold the initial settings block.** Flagged as worth having,
  but deferred — whether it writes `settings.py` directly or only prints a recommended block for the
  developer to paste in is its own decision, not one to make as a side effect of this ADR. (This is a
  distinct, still-unbuilt idea from ticket #51's amendment below, which reuses the `init` name for
  `migrate` itself rather than for a settings-scaffolding tool.)

## Consequences

**`APIVER_MAX_LIVE_VERSIONS`'s counting semantics are a separate, open question**, filed as #41: whether a
Deprecated or Sunset version should stop counting toward the cap. Surfaced while resolving item 5 above,
but it's a disagreement with ADR 0004 item 8's already-shipped reasoning, not a consequence of this
decision — resolved independently.

**`migrate`'s existing `--prefix` CLI flag needs reconciling with `APIVER_ROOT_PREFIX`** in the follow-up
build ticket — most likely `--prefix` becomes optional, inferred from settings when unset, but the exact
CLI shape (and whether `--prefix` keeps its current "which routes count as in-scope for adoption" meaning
alongside the new setting, or is subsumed by it entirely) is left to that ticket.

**ADR 0003 item 2's directory-shape system check gains a stronger guarantee than it had.** A mis-named
version directory used to be merely flagged by `manage.py check`; it's now structurally unreachable,
since `APIVER_VERSION_ROOTS`'s removal (item 4) means nothing ever derives a path to it in the first
place.

**Amendment (ticket #47): item 7's `mount` command generates a new version's `registry.py`, revising
ADR 0003 item 4's "authored versions are hand-written" framing.** The follow-up build ticket found
that hand-writing `derive()` plus the schema/docs wiring on every new version was pure boilerplate a
developer had no reason to type themselves, and — worse — an easy place to forget the schema/docs
override entirely, silently leaving a version serving its parent's schema/docs document under its own
path (the same class of bug ADR 0001 item 4/ticket 22 already found and fixed for the Base Version).
`apiver mount <version> --from <parent>` now generates `registry.py` from scratch — one shot, same
"refuses to regenerate" posture as `migrate`'s Base Version file — with `<version> =
<parent>.derive(<version>)` and both `schema/` and `docs/` always wired (`override()` or `register()`,
whichever the parent's chain already resolves). Only the version's actual Delta — its own
`register()`/`override()`/`remove()` calls for changed endpoints — stays a hand-edit to the file
`mount` just created.

**Amendment (ticket #46): an Alias gets the same conventional-home, derived-path treatment item 5 gave
`APIVER_VERSIONS`, via a new `apiver alias <name> --from <version>` command.** Review pushback on #45
noted that, unlike a Version, an Alias had no fixed filesystem home — `Alias("stable", target=v2)` could
be declared anywhere — making `APIVER_ALIASES`'s `{alias_name: "dotted.path"}` shape (ADR 0003 item 9)
the one place a dotted path was still typed by hand after item 5 removed the equivalent for Versions.
Decided: an Alias's conventional home is the Aggregation Root itself — already where `stable =
Alias(...)` tended to live in practice — so `APIVER_ALIASES` narrows to a plain list of names, e.g.
`["stable"]`, with each name's `Alias` instance derived the same way item 5 derives a Version's:
`f"{APIVER_ROOT_DIR}.urls.{name}"`.

`apiver alias <name> --from <version>` writes only the Aggregation Root's `urls.py` — appending
`<name> = Alias(<name>, target=<version>)` and its `path()` entry — never `settings.py`, the same
posture `mount` already has (item 7); it prints a reminder to add `<name>` to `APIVER_ALIASES` instead.
Schema and docs need no separate wiring: `Alias.urls` already re-includes whatever the target Version
registered under `schema/`/`docs/`, so mounting the alias is enough (ADR 0002 items 22-23). `--from` must
name a Version already mounted in the Aggregation Root — never another Alias, since a chained alias would
silently follow its target's target if repointed, which nothing today would signal — and the command
refuses a name that collides with an already-mounted Version's, since both share one URL-prefix namespace
under the Aggregation Root.

**ADR 0003 item 2's directory-shape system check gains an Alias counterpart.** A new check validates
that every `APIVER_ALIASES` entry resolves at its derived path and is an `Alias` instance — the same
proactive `manage.py check` guarantee item 5's amendment above already gives a misconfigured
`APIVER_VERSIONS` entry, extended to the one setting that still named a path by hand.

**Amendment (ticket #51): `migrate` is renamed `init` — the first command every project runs,
adopted or greenfield — not the separate settings-scaffolding tool this ADR's Considered Options
flagged and deferred under the same name.** Review on #50 (#47) observed that `migrate` had stopped
being adoption-only in practice: every project, including one with no pre-existing API at all, needs
its Base Version's `registry.py` and Aggregation Root generated before anything else can happen, and
"migrate" reads as though it only applies to the adoption case. `apiver init` (`write_init`,
`InitError` — renamed from `write_registry`/`MigrateError` in `apiver.drf.init`, formerly
`apiver.drf.migrate`) keeps `migrate`'s exact adoption behavior unchanged; only the name moves. A
project with genuinely nothing under `APIVER_ROOT_PREFIX`/`--prefix` no longer refuses with "nothing
to migrate" — `discover()` always emits a schema and a docs plan even when nothing else was found
under `--prefix`, registering both unconditionally at `schema/`/`docs/` exactly as `mount` already
does for every later version (item 7's amendment above), so a route-less Base Version is a valid
outcome, not a failure. A pre-existing schema/docs route, once discovered, keeps its own
version-qualified name as before — the default only fills the gap when nothing was there to rename.
