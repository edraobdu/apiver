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

## Switching schemes mid-project

`APIVER_VERSION_SCHEME` is a project-wide setting, not a per-version one — and it applies to every
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
