# Version Schemes

Version names default to plain sequential slugs — `v1`, `v2`, … — and that stays every existing
project's behavior with zero changes. A project can opt into `semver`- or date-shaped names instead via
one project-wide setting:

```python
APIVER_VERSION_SCHEME = "semver"  # or "date"; unset defaults to "sequential"
```

| Scheme | Slug (what you type) | Display Name (what shows up in URLs) |
| --- | --- | --- |
| `sequential` (default) | `v1`, `v2` | same as the slug |
| `semver` | `v1_2_3` | `v1.2.3` |
| `date` | `d2026_08_11` | `2026-08-11` |

`apiver mount`, `apiver init`, and `apiver alias --from` validate every version name against the
configured scheme before writing anything, failing loud on a non-conforming name rather than silently
accepting a typo. The Display Name surfaces in the generated Aggregation Root and
`schema_view(prefix=...)` URL text (e.g. `/api/v1.2.3/`) — the module dotted path, the Django instance
namespace, and the version-suffix class-name check all keep the raw slug unchanged, since a Python
identifier can't contain dots.

An optional `_label` suffix (`v1_2_3_testing`) gives a branch or testing name a legal shape without
making it a chronological point. `apiver alias`'s own name is exempt from scheme validation — it's a
human label (`stable`, `latest`), not a version point — but its `--from` target is still validated as a
real, scheme-conforming version.

## Class names under `semver`/`date`

`_check_suffix` traces every registered class back to the Version that owns it by requiring the
Version's slug, uppercased, as a substring of the class name — `Version("v1_2_3")` requires `V1_2_3`
somewhere in the name, e.g. `UserViewSetV1_2_3`; `Version("d2026_08_11")` requires `D2026_08_11`, e.g.
`UserViewSetD2026_08_11`. That's not idiomatic PascalCase, and it isn't meant to be: dots and hyphens
are illegal in Python identifiers, so the slug itself already stands in underscores for the Display
Name's dots, and the class name just carries that same slug forward. There's no separate, friendlier
suffix convention to opt into — the substring check needs the literal slug, unambiguously, so
drf-spectacular never collides two same-named classes from different versions into one schema
component.

## How many `Version`s does a `semver` project actually need?

Not one per release. A `Version` exists to hold a delta that has to be served *alongside* the version
it derives from — that's what a route resolving differently per client actually requires. A semver
minor or patch bump is backward-compatible by definition, so there's nothing to dual-serve: it's an
ordinary code change to the existing Base Version (or whichever Version already owns that code), no
`register()`/`override()`, no new module, no new suffixed class. Reserve minting a new `Version` — and
the class-naming ceremony that comes with it — for the major bumps that actually break the served
shape, e.g. `v1_0_0` → `v2_0_0`. A project versioning at patch granularity inside apiver is usually a
sign the change didn't need a new `Version` at all.

## Choosing a scheme at adoption time

`APIVER_VERSION_SCHEME` is a genuinely free choice the moment you adopt apiver, regardless of how your
project versioned things before. `apiver init --base ...` creates the very first version its
name-validation ever sees, so whatever ad-hoc numbering the project used up to that point — sequential,
inconsistent, or nonexistent — doesn't constrain the choice at all. Set `APIVER_VERSION_SCHEME` to
`semver` or `date` before running `apiver init` and the Base Version is validated against it directly;
apiver never inspects, and doesn't care about, the mechanics of whatever came before it.

## Switching schemes after apiver is already tracking versions

Once apiver *is* tracking Live versions, the scheme is no longer free to change on a whim — this is a
different situation from the one above. `APIVER_VERSION_SCHEME` is a project-wide setting, not a
per-version one — and it applies to every
*currently Live* version, not just newly-mounted ones: `manage.py check` re-derives the manifest on
every run, which re-validates every name in `APIVER_VERSIONS` against whichever scheme is configured
right now. Flip `APIVER_VERSION_SCHEME` to `semver` while `v1`/`v2` (plain `sequential` names) are still
listed there, and the very next `manage.py check` fails loudly — `v1` doesn't match `semver`'s pattern
either, not just the version you meant to change.

So a scheme switch isn't a same-day, mid-flight flip — it's clean once the old scheme's versions are no
longer in `APIVER_VERSIONS` (archived via [`apiver remove`](version-lifecycle.md#archiving-a-squashed-away-version),
same as retiring any other version). You're not locked into whatever scheme your project started with
forever, but today a project can't run two schemes across simultaneously-Live versions — the switch
happens at the point where the old scheme's versions have already been archived, not before.

See [ADR 0008](https://github.com/edraobdu/apiver/blob/master/docs/adr/0008-version-schemes.md) for the
full design rationale.
