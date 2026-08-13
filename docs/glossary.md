# Glossary

apiver composes complete REST API versions from deltas: a base version defines the whole API, and each
later version declares only what changed. Unchanged routes resolve back through the chain, so every
version presents a full API surface without duplicating it.

Every capitalized term used throughout these docs is defined precisely here — this is the vocabulary the
rest of the site, the README, and apiver's own error messages all speak.

## Versions

**Version**
: A named surface of the API — `v1`, `v2` — mutable while under construction and immutable once
Frozen. Any number of Versions may derive from the same parent; an unpromoted one (an
experiment tried and abandoned) is not a distinct kind of Version, just one nobody pointed an
Alias at for long.
*Avoid: release, revision.*

**Frozen**
: The one-way state change that ends a Version's mutability, entered explicitly rather than on a
schedule or as a side effect of deployment. A Version may be derived from, registered to, and removed
from freely before this point; attempting any of those after raises.
*Avoid: locked, published, released — a Version can be Frozen without ever being deployed.*

**Base Version**
: The one version with no parent, from which every other derives. Its code may live anywhere in the
project and is discovered rather than relocated.
*Avoid: root version, v1 — which is a name, not a role.*

**Authored Version**
: Any version with a parent, written by the developer as a Delta. Its code, like the Base
Version's, may live anywhere in the project and is discovered rather than relocated — having a parent,
not layout, is what distinguishes it from the Base Version.
*Avoid: child version, derived version.*

**Alias**
: A movable name pointing at a Version — `stable`, `latest`, `testing`. Aliases are convenience routes,
not version identifiers; the Version an alias names may change, a Version's meaning may not. Declared
and mounted directly in the Aggregation Root by convention (`apiver alias`) — an
Alias has no package of its own the way a Version does.
*Avoid: channel, tag.*

**Delta**
: The set of overrides and removals one Version declares against its parent.
*Avoid: patch, diff — reserved for schema comparison — or migration — reserved for `apiver init`.*

**Scheme**
: The project-wide convention (`APIVER_VERSION_SCHEME`) that gives a Version's name shape: validates it,
formats it into a Display Name, and orders it chronologically against other names in
the same scheme. One of `sequential` (default), `semver`, or `date`. A Version's `name` is always its
Scheme-conforming Slug, never the Display Name.
*Avoid: version format, naming convention — too vague; Scheme is the specific, declared thing.*

**Slug**
: A Version's actual `name` — the Python-identifier-safe string stored and used everywhere in code
(module paths, class-name suffix, Django namespace). Distinct from its Display Name, which a Scheme
derives from it for presentation only.
*Avoid: version string, identifier — ambiguous with Route Identity.*

**Display Name**
: The human-readable form a Scheme formats a Slug into for presentation — `v1_2_3` becomes `v1.2.3`.
Surfaces only in CLI output, the Manifest, and literal URL path segments — never anywhere
Python-identifier-constrained.
*Avoid: version name — ambiguous with Slug, which is informally "the version's name" too.*

**Label**
: An optional trailing component on a Slug (`v1_2_3_testing`) marking a branch/testing variant that is
scheme-legal but not a chronological point — displays as `v1.2.3-testing`, sorts beside its base point
rather than into the timeline.
*Avoid: suffix — ambiguous with the class-name suffix check — or tag, reserved informally for Alias.*

## Routing

**Route**
: One entry in a Version's resolution table, keyed by its absolute path pattern.
*Avoid: endpoint, URL.*

**Route Identity**
: The metadata carried alongside a Route — `basename`, `action`, `detail`, `url_name`, `methods` — read
from the URLconf rather than inferred. Distinct from the Route's key, which is always the path.
*Avoid: operation id — that is an OpenAPI artifact derived from the path.*

**Registry**
: The one file every Version's root must contain (`registry.py`) — where that Version's
`register()`/`override()`/`remove()` calls happen. The only layout apiver enforces; everything else a
Version needs (serializers, views, ...) is imported into it from wherever the project already keeps
that code, never required to live alongside it.
*Avoid: manifest — reserved for `apiver.toml`, a separate generated artifact.*

**Registration**
: One declaration binding a handler into a Version — a ViewSet at a prefix, or a single view at a path.
A ViewSet Registration expands into several Routes. A Registration is the smallest unit that may be
overridden or removed.
*Avoid: mount, entry.*

**Override**
: A Registration in an authored Version that replaces the parent's Registration of the same name.
*Avoid: patch, shadow.*

**Removal**
: A declaration that a parent's Registration does not exist in this Version. Distinct from simply not
overriding it, which inherits it.
*Avoid: delete, exclude.*

**Resolution**
: Walking the Version chain to determine which handler serves a given path.
*Avoid: lookup, dispatch — DRF's term for method routing within a view.*

**Composition**
: Building a Version's complete resolution table from its parent's table plus its own Delta.
*Avoid: merging, flattening — reserved for squash.*

**Aggregation Root**
: The generated, hand-maintained module (`<root package>/urls.py`) that composes every Live Version's
mount, one `include()` per Version, each already carrying its full absolute path. The project's actual
root `urls.py` includes it once, at an empty prefix, and never changes again as Versions are added. Also
where every Alias is declared and mounted — `apiver alias` appends here, since an Alias has no package
of its own.
*Avoid: root urls, api urls — ambiguous with the project's own true root `urls.py`.*

**Root Directory**
: The dotted path to the package holding the Aggregation Root and every Version's own package
(`APIVER_ROOT_DIR`, e.g. `"apiversions"`) — a filesystem fact. Every Version's package is derived from
it as `f"{ROOT_DIR}.{name}"`; nothing names a Version's directory independently.
*Avoid: root — ambiguous between this and Root Prefix, the split this term exists to resolve.*

**Root Prefix**
: The absolute URL path every Version mounts under (`APIVER_ROOT_PREFIX`, e.g. `"api/"`) — a routing
fact, distinct from Root Directory. Combined with a Version's own name, it is what every Aggregation
Root entry and every `schema_view(prefix=...)` call is built from.
*Avoid: root, prefix alone — `init`'s own `--prefix` flag names a related but not identical thing: which
pre-existing routes count as in scope for adoption.*

**Serving Version**
: The Version a request resolved into, carried on the request from the moment its mount is entered.
Distinct from the Version a handler was *registered* in — one Registration is inherited by many
Versions, so only the request can say which one is serving. Read by gating, by version-aware link
generation, and by any version-conditional logic in a view or serializer.
*Avoid: current version, active version — reads as "in development," per Live.*

## Lifecycle

**Manifest**
: The record of every Version, its lineage, status, aliases and resolution map — a generated snapshot,
not a source of truth. Read by the CLI and squash; version gating reads live `Version` objects instead,
never the manifest.
*Avoid: registry — DRF's term for a router's route list — or config.*

**Squash**
: Flattening an authored Version's inheritance chain into standalone source, so earlier Versions can be
deleted.
*Avoid: merge, collapse.*

**Deprecation**
: The state of a Version that still serves but signals it will eventually Sunset. Declared on the
Version itself; the Manifest reflects it but never originates it. Independent of Frozen — a Deprecated
Version remains mutable and still counts as Live until separately Frozen and Archived.
*Avoid: sunset — a stricter, later state.*

**Sunset**
: The point after which a deprecated Version stops serving and returns `410`. Distinct from deprecation,
which warns while still serving.
*Avoid: retirement, EOL.*

**Live**
: The state of a Version currently mounted in the URLconf — includes Deprecated and Sunset Versions,
since a Sunset Version still needs its mount to answer with `410`. Ends only when the Version is
Archived, not when it Sunsets.
*Avoid: active — reads as "currently in development," the opposite of what's meant.*

**Archived**
: The state of a Version once its mount is removed from the URLconf. Its code may still exist on disk —
an Archived Version is not necessarily a Squashed or deleted one — but it stops counting as Live.
*Avoid: removed, deleted.*
