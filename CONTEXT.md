# apiver

apiver composes complete REST API versions from deltas: a base version defines the whole API, and each
later version declares only what changed. Unchanged routes resolve back through the chain, so every
version presents a full API surface without duplicating it.

## Language

### Versions

**Version**:
A named surface of the API — `v1`, `v2` — mutable while under construction and immutable once Frozen. A
path means the same thing under a Frozen version for as long as that version exists. Any number of
Versions may derive from the same parent; an unpromoted one (an experiment tried and abandoned) is not a
distinct kind of Version, just one nobody pointed an Alias at for long.
_Avoid_: release, revision

**Frozen**:
The one-way state change that ends a Version's mutability, entered explicitly rather than on a schedule or
as a side effect of deployment. A Version may be derived from, registered to, and removed from freely
before this point; attempting any of those after raises.
_Avoid_: locked, published, released (a Version can be Frozen without ever being deployed)

**Base Version**:
The one version with no parent, from which every other derives. Its code may live anywhere in the project
and is discovered rather than relocated.
_Avoid_: root version, v1 (which is a name, not a role)

**Authored Version**:
Any version with a parent, written by the developer as a delta and required to live in apiver's layout.
_Avoid_: child version, derived version

**Alias**:
A movable name pointing at a Version — `stable`, `latest`, `testing`. Aliases are convenience routes, not
version identifiers; the Version an alias names may change, a Version's meaning may not.
_Avoid_: channel, tag

**Delta**:
The set of overrides and removals one Version declares against its parent.
_Avoid_: patch, diff (reserved for schema comparison), migration (reserved for `apiver migrate`)

### Routing

**Route**:
One entry in a Version's resolution table, keyed by its absolute path pattern.
_Avoid_: endpoint, URL

**Route Identity**:
The metadata carried alongside a Route — `basename`, `action`, `detail`, `url_name`, `methods` — read
from the URLconf rather than inferred. Distinct from the Route's key, which is always the path.
_Avoid_: operation id (that is an OpenAPI artifact derived from the path)

**Registration**:
One declaration binding a handler into a Version — a ViewSet at a prefix, or a single view at a path. A
ViewSet Registration expands into several Routes. A Registration is the smallest unit that may be
overridden or removed.
_Avoid_: mount, entry

**Override**:
A Registration in an authored Version that replaces the parent's Registration of the same name.
_Avoid_: patch, shadow

**Removal**:
A declaration that a parent's Registration does not exist in this Version. Distinct from simply not
overriding it, which inherits it.
_Avoid_: delete, exclude

**Resolution**:
Walking the Version chain to determine which handler serves a given path.
_Avoid_: lookup, dispatch (which is DRF's term for method routing within a view)

**Composition**:
Building a Version's complete resolution table from its parent's table plus its own Delta.
_Avoid_: merging, flattening (reserved for squash)

**Aggregation Root**:
The generated, hand-maintained module (`<root package>/urls.py`) that composes every Live Version's
mount, one `include()` per Version, each already carrying its full absolute path. The project's actual
root `urls.py` includes it once, at an empty prefix, and never changes again as Versions are added
(ADR 0007).
_Avoid_: root urls, api urls (ambiguous with the project's own true root `urls.py`)

**Root Directory**:
The dotted path to the package holding the Aggregation Root and every Version's own package
(`APIVER_ROOT_DIR`, e.g. `"api"`) — a filesystem fact. Every Version's package is derived from it as
`f"{ROOT_DIR}.{name}"`; nothing names a Version's directory independently (ADR 0007).
_Avoid_: root (ambiguous between this and Root Prefix — the split this term exists to resolve)

**Root Prefix**:
The absolute URL path every Version mounts under (`APIVER_ROOT_PREFIX`, e.g. `"api/"`) — a routing fact,
distinct from Root Directory. Combined with a Version's own name, it is what every Aggregation Root entry
and every `schema_view(prefix=...)` call is built from (ADR 0007).
_Avoid_: root, prefix alone (migrate's own `--prefix` flag names a related but not identical thing: which
pre-existing routes count as in scope for adoption)

**Serving Version**:
The Version a request resolved into, carried on the request from the moment its mount is entered.
Distinct from the Version a handler was *registered* in — one Registration is inherited by many
Versions, so only the request can say which one is serving (ADR 0005). Read by gating, by
version-aware link generation, and by any version-conditional logic in a view or serializer.
_Avoid_: current version, active version (which reads as "in development", per Live)

### Lifecycle

**Manifest**:
The record of every Version, its lineage, status, aliases and resolution map — a generated snapshot, not a
source of truth. Read by the CLI and squash; version gating reads live `Version` objects instead, never the
manifest (ADR 0003).
_Avoid_: registry (which is DRF's term for a router's route list), config

**Squash**:
Flattening an authored Version's inheritance chain into standalone source, so earlier Versions can be
deleted.
_Avoid_: merge, collapse

**Deprecation**:
The state of a Version that still serves but signals it will eventually Sunset. Declared on the Version
itself; the Manifest reflects it but never originates it.
_Avoid_: sunset (a stricter, later state)

**Sunset**:
The point after which a deprecated Version stops serving and returns 410. Distinct from deprecation,
which warns while still serving.
_Avoid_: retirement, EOL

**Live**:
The state of a Version currently mounted in the URLconf — includes Deprecated and Sunset Versions, since
a Sunset Version still needs its mount to answer with 410. Ends only when the Version is Archived, not
when it Sunsets.
_Avoid_: active (reads as "currently in development," the opposite of what's meant)

**Archived**:
The state of a Version once its mount is removed from the URLconf. Its code may still exist on disk — an
Archived Version is not necessarily a Squashed or deleted one — but it stops counting as Live.
_Avoid_: removed, deleted
