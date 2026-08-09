# apiver

apiver composes complete REST API versions from deltas: a base version defines the whole API, and each
later version declares only what changed. Unchanged routes resolve back through the chain, so every
version presents a full API surface without duplicating it.

## Language

### Versions

**Version**:
An immutable, named snapshot of the API surface — `v1`, `v2`. A path always means the same thing under
the same version.
_Avoid_: release, revision

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

### Lifecycle

**Manifest**:
The record of every Version, its lineage, status, aliases and resolution map. Read by version gating, the
CLI, and squash.
_Avoid_: registry (which is DRF's term for a router's route list), config

**Squash**:
Flattening an authored Version's inheritance chain into standalone source, so earlier Versions can be
deleted.
_Avoid_: merge, collapse

**Sunset**:
The point after which a deprecated Version stops serving and returns 410. Distinct from deprecation,
which warns while still serving.
_Avoid_: retirement, EOL
