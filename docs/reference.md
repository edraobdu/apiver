# Reference

Quick lookup for the CLI and settings. For the reasoning behind any of these, see
[Getting Started](getting-started.md) and the [Guides](guides/version-lifecycle.md).

## CLI

`apiver` is a standalone command, not a `manage.py` subcommand, so it can introspect a project offline.
`init`, `mount`, `alias`, `manifest`, `diff`, and `check` need Django settings resolved (`--settings`,
then `DJANGO_SETTINGS_MODULE`, then `[tool.apiver].django_settings_module` in `pyproject.toml`);
`versions` reads only the committed `apiver.toml` and needs neither.

| Command | What it does |
| --- | --- |
| `apiver init --base NAME [--prefix PATH ...]` | Adopts an existing project's routes as the base version named `NAME`, or scaffolds a route-less one — moves nothing. `--prefix` is repeatable for routes scattered across several unrelated ancestors. |
| `apiver mount NAME --from PARENT` | Scaffolds a new authored version's `registry.py`, derived from `PARENT`, with schema/docs already wired. |
| `apiver alias NAME --from VERSION` | Declares a movable name pointing at an already-mounted version. |
| `apiver manifest [--check]` | Writes `apiver.toml`, a committed snapshot of every version's resolution table; `--check` exits non-zero if it's stale, the same idiom as `makemigrations --check`. |
| `apiver versions` | Prints lineage, frozen status, lifecycle state, alias pointers, and defined-vs-inherited routes per version — reading only the manifest, without booting the project. |
| `apiver diff OLD NEW [--json]` | Compares two versions' composed OpenAPI schemas, plus each shared registration's `permission_classes`/`authentication_classes`/`pagination_class`/`filter_backends`/`throttle_classes`/`ordering`, and reports every field/resource/attribute change between them — human-readable by default, `--json` for tooling. Always prints the schema-diff blind-spots disclaimer alongside the result. |
| `apiver check [VERSION ...]` | CI-facing wrapper around `diff`: prints every authored live version's diff against its parent (or just the versions named). Every reported change already came from an explicit `register()`/`override()`/`remove()` call, so `check` reports rather than gates — it exits non-zero only on a tool/config error, never because a diff found changes. |
| `apiver squash VERSION` | Makes `VERSION`'s `registry.py` an explicit, complete list of every route it resolves from its whole ancestor chain — see [Version lifecycle](guides/version-lifecycle.md#squashing-a-long-delta-chain). Its parent chain is left untouched. Refuses, writing nothing, if any absorbed version doesn't satisfy the registry-only rule from [Philosophy](philosophy.md). Auto-applied to `VERSION`'s `registry.py`; never deletes anything. |
| `apiver remove VERSION [--force]` | Archives `VERSION` — see [Version lifecycle](guides/version-lifecycle.md#archiving-a-squashed-away-version). Cuts every direct child's parent link (each becoming its own independent Base Version) and drops `VERSION`'s mount from the Aggregation Root. Refuses, writing nothing, unless every direct child already resolves `VERSION`'s entire contribution explicitly, or if `VERSION` was never deprecated (`--force` overrides that). Never touches `settings.py`; never deletes `VERSION`'s directory. |

## Settings

| Setting | Purpose |
| --- | --- |
| `APIVER_ROOT_DIR` | Dotted path to the package holding the Aggregation Root and every version's own package. Defaults to `"apiversions"` — deliberately not `"api"`, so it never collides with a project's own pre-existing API app when adopting apiver into an existing project. |
| `APIVER_ROOT_PREFIX` | Absolute URL path every version mounts under. |
| `APIVER_VERSIONS` | Hand-maintained list of live version names. |
| `APIVER_ALIASES` | Hand-maintained list of declared alias names. |
| `APIVER_VERSION_SCHEME` | The project's version-naming Scheme — `sequential` (default), `semver`, or `date` — used to validate, format, and chronologically order version names. See [Version schemes](guides/version-schemes.md). |
| `APIVER_MAX_LIVE_VERSIONS` | Warning-level system check threshold for live versions (default **3**) — a maintenance-burden signal, not a hard limit; pair with `manage.py check --fail-level WARNING` in CI if you want it hard. |
| `APIVER_MANIFEST_PATH` | Where `apiver.toml` is read/written, if not the project root. |
| `APIVER_OUT_OF_BAND_ALIAS` | Alias namespace `apiver.drf.reverse` falls back to for code with no request in reach (a Celery task, a management command) — set to your rolling `Alias` (`stable`), not a fixed version. See [Version-aware links](guides/version-aware-links.md). |
| `APIVER_PATCH_HYPERLINKED_FIELDS` | Set to `False` to opt out of apiver's version-aware `HyperlinkedRelatedField.get_url` patch. |

## Requirements

- Python 3.12–3.14
- Django ~5.2
- Django REST Framework ~3.18
- drf-spectacular ~0.30

## Installation

```console
$ uv add apiver
```

or with `pip`:

```console
$ pip install apiver
```
