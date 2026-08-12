---
status: accepted
---

# Version identity stays a single Slug; a project-wide Scheme derives display formatting, validation, and chronological order from it

apiver users increasingly want version names that read as semver (`v1.2.3`) or ISO dates (`2026-08-11`,
à la Stripe), not just sequential integers. Both are illegal as literal `Version` names today: Python
identifiers can't contain dots, hyphens, or start with a digit, and `Version.name` is string-interpolated
directly into dotted module paths, Django instance namespaces, and `_check_suffix`'s class-name substring
check (`version.py:128-137,188-218`). This ADR decides how apiver supports those styles without breaking
that constraint.

## Decision

1. **Version identity stays one string — the Slug.** No dual display-name/slug type on `Version` itself.
   Every Python-identifier-constrained surface (module dotted path, Django instance namespace/app_name,
   `_check_suffix`'s substring check) keeps reading the raw Slug, unchanged.

2. **A project-wide Scheme derives everything else.** One new setting, `APIVER_VERSION_SCHEME`, names the
   project's scheme. It supplies three operations: validate a Slug's shape, format a Slug into a Display
   Name, and compare two Slugs chronologically. Declared once per project, not per-Version — mixing
   schemes within one project is not supported.

3. **Three built-in schemes, closed set:**
   - `sequential` (default when unset): slug `v1`, `v2`, …; display equals slug — today's behavior,
     unchanged.
   - `semver`: slug `v1_2_3` (underscores standing in for the dots); display `v1.2.3`.
   - `date`: slug `d2026_08_11`; display `2026-08-11`.

   No pluggable/custom-scheme interface yet — this project's established posture (ADR 0003) is to not
   build structure ahead of a concrete need.

4. **An optional Label suffix, uniform across all three schemes**, gives branch/testing names a legal
   shape without being a chronological point: `v1_2_3_testing` displays as `v1.2.3-testing` and is
   excluded from strict chronological ordering — it sorts alongside its base point rather than being
   forced into the timeline.

5. **Validation is strict and happens at CLI time**, as early as the information exists: `apiver mount
   <version_name> --from <from_version>` and `apiver init`'s base-version name are validated against the
   scheme before any scaffold file is written, failing loud with the existing `InitError` pattern.
   `apiver alias <name>` is exempt — an alias name is a human label (`stable`, `latest`), not a version
   point — but its `--from` target is still validated as a real, scheme-conforming version name.

6. **Composition order and chronological order are independent, on purpose.** The existing `.derive()`
   parent chain controls override resolution and is already a branching tree, not a total order — `v2`
   and `v1_testing` can both derive from `v1`. Scheme-based chronological sort controls display order only
   (`apiver versions`, the manifest, docs) and has no bearing on composition. No system check
   cross-validates the two: a testing branch legitimately derives from an older point than the
   chronologically newest real version.

7. **Display Name surfaces in CLI output, the manifest, and the literal URL path segment** (Django path
   converters accept dots and hyphens there, e.g. `/api/v1.2.3/`) — never in anything
   Python-identifier-constrained.

## Considered options

- **Dual identity** (separate display-name and slug fields on `Version`, developer supplies or derives
  both independently). Rejected: adds a second identity concept everywhere `Version.name` is already used,
  for a problem a Scheme's formatter already solves by deriving the Display Name from the one stored Slug.
- **Per-Version scheme declaration.** Rejected in favor of one project-wide setting — a project mixing
  semver and date-based versions in the same `APIVER_VERSIONS` list has no coherent chronological order to
  sort by, and nothing in this design needs mixing.
- **Auto-detecting a version's scheme from its shape.** Not considered seriously — consistent with ADR
  0007 item 1's existing rejection of "version-shaped" path auto-detection; a wrong guess is worse than an
  explicit setting.
- **Escape hatch for non-conforming names** (any string allowed, unparseable ones just skip
  formatting/sorting). Rejected in favor of strict validation once the Label-suffix grammar (item 4) gave
  every legitimate testing/branch case a way to conform — an unconstrained escape hatch would silently
  accept typos indistinguishable from a bug.
- **Cross-validating composition order against chronological order.** Considered so `.derive()` couldn't
  produce a "newer" version from an "older" chronological point. Rejected: real testing/staging workflows
  need exactly that (a `v1_testing` branch derived from `v1` while `v2` also exists) — the two orders
  answer different questions, and forcing agreement would forbid a legitimate pattern.
- **Display form everywhere, including the Django instance namespace.** Rejected: Django
  namespaces/app labels carry the same identifier constraints as Python — no dots. Only the literal URL
  text (a Django path converter's job, not Python's) can safely carry the Display Name.

## Consequences

Every existing project keeps working with zero changes — `APIVER_VERSION_SCHEME` unset defaults to
`sequential`, exactly today's `v1`/`v2` behavior. Anything outside apiver's own CLI/manifest/URL-path
surfaces that reads `Version.name` directly (e.g. a hand-written template) sees the raw Slug — Display
Name formatting is not automatically threaded through every possible integration point, only the three
named in item 7.

Left to the build ticket: whether hand-authored `Version("v1_2_3")` construction in a hand-edited
`registry.py` (bypassing `apiver mount`'s CLI-time validation entirely) should also be checked — e.g. via
a Django system check mirroring the directory-shape check's existing idiom (ADR 0003 item 2) — or whether
CLI-time validation alone is judged sufficient since `mount` is the only supported way to create an
authored version's scaffold.
