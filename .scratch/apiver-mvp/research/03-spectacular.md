# 03 — drf-spectacular: per-version schemas without collisions

Research report for ticket [03-spectacular-integration](../issues/03-spectacular-integration.md).

**Sources read (all primary, pinned):**

| Project | Version | How verified |
|---|---|---|
| drf-spectacular | **0.30.0** (released 2026-07-06) | `https://pypi.org/pypi/drf-spectacular/json` → `info.version = "0.30.0"`, `upload_time_iso_8601 = 2026-07-06T11:29:45Z`; full source read at tag `0.30.0` (tarball `https://github.com/tfranzel/drf-spectacular/archive/refs/tags/0.30.0.tar.gz`) |
| — its Django/DRF target | Django 2.2–6.0, DRF 3.10–3.17, Python 3.8–3.14 | `requirements/base.txt` → `Django>=2.2`, `djangorestframework>=3.10.3`; `tox.ini:1-17` envlist (highest tested combination: `py314-django6.0-drf3.17`); PyPI classifiers list `Framework :: Django :: 2.2 … 6.0`. **There are no DRF classifiers on PyPI** — DRF support is only assertable from `tox.ini` and the dependency floor. DRF 3.18.0 (2026-08-07) postdates 0.30.0 and is *not* in the matrix. |
| oasdiff | v1.28.0 (2026-08-06) | GitHub API `repos/oasdiff/oasdiff` + `releases/latest`; `docs/*.md` at `main` |
| openapi-changes | v0.2.10 (2026-07-01) | GitHub API `repos/pb33f/openapi-changes`; `README.md` at `main`; `pb33f.io/openapi-changes/summary/` |
| OpenAPITools/openapi-diff | 2.1.7 (2026-01-26) | GitHub API `repos/OpenAPITools/openapi-diff`; `README.md` at `master` |

All `file:line` references below are to drf-spectacular **0.30.0** unless stated otherwise. Raw file
URL pattern: `https://raw.githubusercontent.com/tfranzel/drf-spectacular/0.30.0/<path>`.

Nothing was installed, no Django was executed, no git repo was created. One stdlib-only CPython probe
was run against **verbatim copies** of three drf-spectacular functions to confirm Python attribute
semantics; it is marked **[probe]** and appears in §3.

---

## 1. Bottom line

**Yes — and if apiver emits one schema document per version, it is close to free; the moment apiver
tries to emit a single combined multi-version document, it becomes real work.** Per-version
generation is a first-class, upstream-tested feature: `SpectacularAPIView.as_view(urlconf=[…])` takes
an explicit list of URL patterns and generates a schema from exactly that subtree
(`views.py:58,66-77,90`; upstream test `tests/test_view.py:27-45,72-83`). Each generator gets its own
`ComponentRegistry` (`generators.py:107`), so two versions generated as two documents cannot collide
with each other at all — `PaymentSerializer` in `v1/` and `PaymentSerializer` in `v2/` each become
component `Payment` in *their own* document, which is exactly the right input for a `diff`. Aliases
are excluded by simply not putting the alias mount in that version's pattern list. In a **combined**
document the two hazards the ticket anticipated are both real: identically-named serializer classes
produce a warning *and a silently wrong schema* — the second class is never mapped, and V2's
endpoints get `$ref`'d to V1's component (`plumbing.py:797-802` + `openapi.py:1696-1697`); and
operationIds collide whenever `SCHEMA_PATH_PREFIX` swallows the version segment, which spectacular
detects, warns about, and "fixes" by appending `_2` (`plumbing.py:1239-1253`). Two further findings
matter more than the ticket assumed. First, **inheritance does confuse it, but not the way expected**:
component names come from `__class__.__name__`, so `PaymentV2Serializer(PaymentV1Serializer)` cleanly
yields `PaymentV2`/`PaymentV1` — *unless* V1 carries `@extend_schema_serializer(...)`, in which case
the undecorated V2 subclass **inherits the parent's `component_name` through normal Python attribute
lookup** and collides with it (§3, verified by probe). Second, **the default auto-estimated
`SCHEMA_PATH_PREFIX` makes operationIds a function of which endpoints happen to be in the document**
(`generators.py:210-220`) — adding one endpoint can rename every operationId in the file. For a tool
whose 0.2 story is diffing generated schemas, apiver must pin `SCHEMA_PATH_PREFIX` per version. Do
that, generate per-version documents, and `diff` gets aligned paths *and* aligned operationIds for
free.

**Recommended shape for apiver** (details in §1–§5):

- one `SpectacularAPIView` per version, `urlconf=<that version's mount list only>`;
- `custom_settings={'TITLE': …, 'VERSION': …, 'SCHEMA_PATH_PREFIX': r'/api/v2'}` per version;
- global `SERVE_INCLUDE_SCHEMA: False` so the schema endpoint is not itself in the diff;
- no combined document in 0.1. If one is ever wanted, namespace operationIds in a
  `POSTPROCESSING_HOOKS` entry (runs *before* collision detection — `generators.py:292-295`) and
  component names in a custom `AutoSchema.get_serializer_name`.

---

## 2. Question 1 — per-version schema generation

### 2.1 Every supported mechanism

There are exactly five knobs, and they compose. In descending order of how well-supported they are:

**(a) `SpectacularAPIView.urlconf` — the documented, upstream-tested route.**

```python
class SpectacularAPIView(APIView):
    ...
    urlconf: Optional[str] = spectacular_settings.SERVE_URLCONF   # views.py:58
    api_version: Optional[str] = None                             # views.py:59
    custom_settings: Optional[Dict[str, Any]] = None              # views.py:60
    patterns: Optional[List[Any]] = None                          # views.py:61
```

`urlconf` accepts three shapes, resolved in `get()` (`views.py:66-77`):

1. a dotted module path string (`'myproj.urls_v2'`) — passed straight through to DRF's
   `EndpointEnumerator`;
2. a list/tuple of dotted module path strings — each is `import_module`'d and their `urlpatterns`
   concatenated into a synthetic `namedtuple('ModuleWrapper', ['urlpatterns'])`;
3. a list/tuple of already-resolved URL pattern objects — wrapped in the same `ModuleWrapper`.

Shape (3) is the one apiver wants, and it is exercised by upstream tests
(`tests/test_view.py:27-45`, asserted in `tests/test_view.py:57-83`):

```python
# tests/test_view.py:27-30  (verbatim)
urlpatterns_v1 = [path('api/v1/pi/', pi)]
urlpatterns_v1.append(
    path('api/v1/schema/', SpectacularAPIView.as_view(urlconf=urlpatterns_v1))
)
```

Note the self-reference: the list is captured by identity and only walked at request time, so
appending the schema view to the very list it will enumerate works.

**(b) `SpectacularAPIView.patterns`** — passed through to the generator as DRF's
`BaseSchemaGenerator(patterns=…)` (`views.py:90`). Functionally similar to `urlconf` shape (3) but it
bypasses `ModuleWrapper`; `urlconf` is the better-tested path and is what the upstream tests use.

**(c) `SERVE_URLCONF` setting** (`settings.py:52-53`, comment: *"Configuration for serving a schema
subset with SpectacularAPIView"*). This is only the **global default** for `SpectacularAPIView.urlconf`
(`views.py:58`). It is a single value, so it cannot by itself produce more than one document — it is
for the "my project has one API subtree and a lot of non-API URLs" case, not the multi-version case.
It is also explicitly **forbidden** in `custom_settings` (`settings.py:257-262` rejects any attribute
starting with `SERVE_` or `DEFAULT_GENERATOR_CLASS`).

**(d) `custom_settings` per view** — documented in the FAQ under *"How can I have multiple
`SpectacularAPIView` with differing settings"* (`docs/faq.rst:328-352`). Applied via a context manager
that mutates the global settings object and restores it afterwards (`settings.py:282-292`,
`views.py:79`). The FAQ carries an explicit warning: *"Beware that using this mechanic is not
thread-safe at the moment."* (`docs/faq.rst:337`). For apiver this is fine for a CLI and acceptable
for a docs endpoint, but it is a caveat worth documenting downstream.

**(e) DRF-versioning-aware filtering (`api_version`)** — `generators.py:236-250`. This is the
mechanism the FAQ points at (`docs/faq.rst:76-89`) and it is **not** apiver's mechanism. It only
engages for views that set a `versioning_class`, and only for
`URLPathVersioning`/`NamespaceVersioning`/`AcceptHeaderVersioning`
(`plumbing.py:1056-1061`); anything else emits *"using unsupported versioning class … view will be
processed as unversioned view"* (`generators.py:236-240`). Its model is **one viewset serving many
versions**, filtered by `@extend_schema(versions=[…])` (`utils.py:361,437-444`) and, for
`URLPathVersioning`, by substituting the `{version}` path variable
(`plumbing.py:1073-1086`). apiver's model is the inverse — distinct classes behind distinct static
prefixes — so with no `versioning_class` set, `api_version` is a no-op for route selection. It still
affects the document header: `build_root_object(version=self.api_version or request.version)`
(`generators.py:283-291`) and `'VERSION': '0.0.0'` becomes `'0.0.0 (v2)'` (`settings.py:204-207`).

**Offline / CLI generation.** `./manage.py spectacular` accepts `--urlconf` (dotted module path
only — *not* a pattern list), `--api-version`, `--custom-settings` (dotted path to a dict),
`--generator-class`, `--file`, `--validate`, `--fail-on-warn`
(`management/commands/spectacular.py:34-87`). It has **no `--patterns`**. So for apiver's future
`diff`/`check`, either:

- generate one module per version exposing `urlpatterns` and shell out per version, or
- call the generator directly in-process:
  `SchemaGenerator(urlconf=…, patterns=…, api_version=…).get_schema(request=None, public=True)`
  (`generators.py:103-111,283-295`). `drf_spectacular.generators.SchemaGenerator` is the value of
  the `DEFAULT_GENERATOR_CLASS` setting and the target of `--generator-class`, so it is a supported
  extension point, though `drf_spectacular.generators` is **not** in the published API reference
  (`docs/drf_spectacular.rst` lists `utils`, `types`, `views`, `extensions`, `hooks`, `openapi`,
  `contrib.django_filters` only).

### 2.2 The trade-off that actually bites: `SCHEMA_PATH_PREFIX`

This is the single most important finding in §2 for apiver's 0.2 story.

```python
# generators.py:210-222 (verbatim)
if spectacular_settings.SCHEMA_PATH_PREFIX is None:
    # estimate common path prefix if none was given. only use it if we encountered more
    # than one view to prevent emission of erroneous and unnecessary fallback names.
    non_trivial_prefix = len(set([view.__class__ for _, _, _, view in endpoints])) > 1
    if non_trivial_prefix:
        path_prefix = posixpath.commonpath([path for path, _, _, _ in endpoints])
        path_prefix = re.escape(path_prefix)  # guard for RE special chars in path
    else:
        path_prefix = '/'
else:
    path_prefix = spectacular_settings.SCHEMA_PATH_PREFIX
```

The default is `None` (`settings.py:13`), i.e. **auto-estimate**. `path_prefix` is then stripped from
the path before tokenisation, and the tokens are what produce both the operationId
(`openapi.py:451-473`) and the tag (`openapi.py:380-384`). Consequences:

- The prefix is `commonpath` over *the endpoints in this document*. A per-version document containing
  only `/api/v2/payments/` and `/api/v2/payments/{id}/export/` (two view classes) estimates
  `/api/v2/payments` — so the list operation tokenises to `[]`, hits the `if not tokenized_path:
  tokenized_path.append('root')` fallback (`openapi.py:462-463`), and is named `root_list`. Add a
  `/api/v2/refunds/` endpoint later and the prefix shrinks to `/api/v2`, renaming *every operationId
  in the document*.
- **A diff tool cannot live with that.** apiver should always pin `SCHEMA_PATH_PREFIX` explicitly
  (per version, via `custom_settings`) so operationIds are a function of the route only.
- There is a genuine tension between tags and operationIds when building a *combined* document:
  `get_tags()` returns the first token, so with prefix `/api` every v1 operation is tagged `v1` and
  every v2 operation `v2`; with prefix `/api/v[0-9]+` the tags become `payments`/`refunds` but the
  version token is gone from the operationId, guaranteeing collisions. Per-version documents dissolve
  the tension: pin `/api/v2`, get `payments` tags *and* clean `payments_list` operationIds.

Two related settings are worth knowing: `SCHEMA_PATH_PREFIX_TRIM` (removes the matched prefix from
the emitted path, `settings.py:14-16`, applied at `generators.py:266-267`) and
`SCHEMA_PATH_PREFIX_INSERT` (`settings.py:17-21`, applied at `generators.py:269-270`). Together they
could rewrite `/api/v2/payments/` to `/payments/` in the document, which would make v1↔v2 diffs align
on path without any prefix-stripping in the diff tool. That is a legitimate option, but it makes the
served document's paths not match the real URLs, so prefer doing the stripping in the diff tool
(oasdiff has `--strip-prefix-base`/`--strip-prefix-revision` for exactly this — §8).

### 2.3 Verdict on question 1

The supported route is **`SpectacularAPIView.as_view(urlconf=<pattern list>, custom_settings={…})`
per version**, with `./manage.py spectacular --urlconf <module>` (or an in-process `SchemaGenerator`)
for offline generation. `SERVE_URLCONF` is a global default, not a multiplexer. `api_version` is for
DRF's own versioning classes and does nothing for statically-prefixed version trees.

---

## 3. Question 3 — component / schema names (answered before question 2; it is the bigger risk)

### 3.1 How the name is derived

`AutoSchema._get_serializer_name` (`openapi.py:1641-1682`), in precedence order:

1. an `OpenApiSerializerExtension.get_name(auto_schema, direction)` returning non-`None`
   (`openapi.py:1642-1651`, `extensions.py:67-69`);
2. `get_override(serializer, 'component_name')` — set by
   `@extend_schema_serializer(component_name=…)` (`openapi.py:1652-1653`, `utils.py:633-634`);
3. `serializer.Meta.ref_name` (drf-yasg compatibility) (`openapi.py:1654-1658`);
4. for a `ListSerializer`, recurse into `.child` (`openapi.py:1659-1660`);
5. otherwise `self.get_serializer_name(serializer, direction)`, whose entire body is
   `return serializer.__class__.__name__` (`openapi.py:1637-1639`).

Then, unconditionally:

```python
# openapi.py:1666-1673
if name.endswith('Serializer'):
    name = name[:-10]
if is_patched_serializer(serializer, direction):
    name = 'Patched' + name
if direction == 'request' and spectacular_settings.COMPONENT_SPLIT_REQUEST:
    name = name + 'Request'
```

So with defaults (`COMPONENT_SPLIT_PATCH: True`, `COMPONENT_SPLIT_REQUEST: False` —
`settings.py:32,36`), `PaymentV1Serializer` → component `PaymentV1`, plus `PatchedPaymentV1` for
`PATCH` bodies. Illegal characters trigger a warning (`openapi.py:1675-1680`).

### 3.2 What happens when V2 inherits V1 — the actual answer

**Case A — plain inheritance, distinct class names, no decorators. No collision, no confusion.**

```python
class PaymentV1Serializer(serializers.ModelSerializer): ...
class PaymentV2Serializer(PaymentV1Serializer): ...
```

Naming is `__class__.__name__`-based and never consults the MRO, so these are `PaymentV1` and
`PaymentV2`. Registry keys are `(name, type)` (`plumbing.py:738-740`), so the keys differ and
`ComponentRegistry.__contains__` never even compares identities (`plumbing.py:776-779`). Both
components are emitted in full, each with its own resolved field set (V2's inherited fields are
re-mapped from the instantiated V2 serializer, not copied by `$ref`). **Spectacular emits no `allOf`
/ inheritance relationship at all** — it flattens; there is no code path in `_map_serializer` that
looks at base classes. So a combined document gets two independent, fully-spelled-out components.
That is verbose but correct, and it is *good* for diffing (no indirection to resolve).

**Case B — identical class names in different modules. Collision, warning, and a silently wrong
schema.** This is the realistic apiver failure mode, because an enforced per-version layout naturally
puts `PaymentSerializer` in both `api/v1/serializers.py` and `api/v2/serializers.py`.

```python
# plumbing.py:793-803 (verbatim)
suppress_collision_warning = (
    get_override(registry_id, 'suppress_collision_warning', False)
    or get_override(query_id, 'suppress_collision_warning', False)
)
if query_id != registry_id and not suppress_collision_warning:
    warn(
        f'Encountered 2 components with identical names "{component.name}" and '
        f'different identities {query_id} and {registry_id}. This will very '
        f'likely result in an incorrect schema. Try renaming one.'
    )
return True
```

Note what `__contains__` returns: **`True`**. And the caller does this:

```python
# openapi.py:1691-1699 (verbatim)
component = ResolvedComponent(
    name=self._get_serializer_name(serializer, direction, bypass_extensions),
    type=ResolvedComponent.SCHEMA,
    object=self.get_serializer_identity(serializer, direction),
)
if component in self.registry:
    return self.registry[component]  # return component with schema

self.registry.register(component)
component.schema = self._map_serializer(serializer, direction, bypass_extensions)
```

So the *second* `PaymentSerializer` is **never mapped**. Every V2 operation gets
`{"$ref": "#/components/schemas/Payment"}` pointing at **V1's fields**. The document is
syntactically valid, passes `--validate`, and is semantically wrong. The only signal is a stderr
warning — which is why `--fail-on-warn` (`management/commands/spectacular.py:55-61`) matters. This is
upstream-tested: `tests/test_warnings.py:22-49` builds two distinct `XSerializer` classes and asserts
`'Encountered 2 components with identical names "X" and different identities'` in stderr.

**Case C — V1 is decorated, V2 inherits. Collision, caused by inheritance.** This is the trap.
`@extend_schema_serializer(component_name=…)` stores into a plain class attribute
(`utils.py:633-634` → `drainage.set_override`), and lookup is a plain `hasattr`
(`drainage.py:153-160`), which walks the MRO:

```python
# drainage.py:153-177 (verbatim)
def has_override(obj, prop):
    if isinstance(obj, functools.partial):
        obj = obj.func
    if not hasattr(obj, '_spectacular_annotation'):
        return False
    if prop not in obj._spectacular_annotation:
        return False
    return True
...
def set_override(obj, prop, value):
    if not hasattr(obj, '_spectacular_annotation'):
        obj._spectacular_annotation = {}
    elif '_spectacular_annotation' not in obj.__dict__:
        obj._spectacular_annotation = obj._spectacular_annotation.copy()
    obj._spectacular_annotation[prop] = value
    return obj
```

**[probe]** — verbatim copies of `has_override` / `get_override` / `set_override` run against plain
classes under stdlib CPython 3.13:

| class | decorated? | `has_override(cls,'component_name')` | `get_override(...)` |
|---|---|---|---|
| `PaymentV1Serializer` | yes, `'PaymentV1'` | `True` | `PaymentV1` |
| `PaymentV2Serializer(PaymentV1Serializer)` | **no** | `True` | **`PaymentV1`** |
| `PaymentV3Serializer(PaymentV1Serializer)` | yes, `'PaymentV3'` | `True` | `PaymentV3` (and V1 still `PaymentV1`) |

So an **undecorated subclass of a decorated serializer silently adopts the parent's component name**
and lands squarely in Case B. The copy-on-write branch in `set_override` (`drainage.py:174-175`)
protects the parent only when the child is *itself* decorated — that is what
`tests/test_regressions.py:2901-2911` (`test_extend_schema_serializer_isolation`) asserts. There is
**no upstream test for the undecorated-subclass case**; the behaviour above is a direct consequence
of the source plus verified Python semantics.

The same inheritance applies to every other `@extend_schema_serializer` argument — `exclude_fields`,
`deprecate_fields`, `many`, `examples`, `description` (`utils.py:622-637`). For apiver, whose whole
premise is "V2 is a subclass of V1", this is a first-class hazard: **a V1 field excluded from the
schema stays excluded in V2 unless V2 re-decorates.**

### 3.3 The `enum` sub-hazard in a combined document

`postprocess_schema_enums` (`hooks.py:15-…`, the sole default `POSTPROCESSING_HOOKS` entry,
`settings.py:100-102`) breaks every `enum` out into its own component, named from the **property
name**, globally across the document (`hooks.py:84-103`):

- property name used for exactly one choice set → `StatusEnum` (`hooks.py:89-91`);
- property name with several choice sets, each confined to one component → `PaymentV1StatusEnum` /
  `PaymentV2StatusEnum` (`hooks.py:92-95`) — no warning;
- otherwise → `Status<hash>Enum` **plus** *"enum naming encountered a non-optimally resolvable
  collision for fields named …"* (`hooks.py:96-103`);
- the same choice set reachable under two names → *"encountered multiple names for the same choice
  set"* (`hooks.py:104-109`).

So in a combined document, changing a `status` choice set between V1 and V2 is handled gracefully
(component-qualified names), but a shared choice set that appears in several components can produce a
hash-suffixed enum name — which is **unstable across content changes** and therefore hostile to
diffing. `ENUM_NAME_OVERRIDES` (`settings.py:116-118`) is the escape hatch. Per-version documents
avoid the whole area: each document names its own `StatusEnum`, and a v1↔v2 diff sees `StatusEnum`'s
values change, which is the truthful report.

### 3.4 Supported hooks to control component naming

| Hook | Where | Public? | Fits apiver? |
|---|---|---|---|
| `@extend_schema_serializer(component_name='PaymentV2')` | `utils.py:599-639` | Yes — in `docs/drf_spectacular.rst` and `docs/customization.rst` "Step 4" | Works, but must be applied to **every** version's serializer, including subclasses (see Case C). Verbose and easy to forget. |
| `Meta.ref_name` | `openapi.py:1654-1658` | Yes (drf-yasg compat) | Same ergonomics, less idiomatic. |
| Subclass `AutoSchema`, override `get_serializer_name(serializer, direction)` | `openapi.py:1637-1639`, marked *"override this for custom behaviour"*; `drf_spectacular.openapi` is in the published API reference | Yes | **Best fit.** One class, set as `DEFAULT_SCHEMA_CLASS`. Can suffix by version derived from `self.path`. Caveat: `self.path` is set in `get_operation` (`openapi.py:71`) and is not itself documented — a mild reach (see §10). |
| `OpenApiSerializerExtension.get_name(auto_schema, direction)` | `extensions.py:67-69`, documented in `docs/customization.rst` "Step 5" | Yes | Good when the serializer classes are not apiver's to decorate. `auto_schema` is handed in explicitly, so deriving the version from the operation path is sanctioned here. Pair with `get_identity` (`extensions.py:71-73`) if two names must map to one component. |
| `COMPONENT_SPLIT_REQUEST` / `COMPONENT_SPLIT_PATCH` | `settings.py:31-36` | Yes | Not a collision fix — they multiply components (`XRequest`, `PatchedX`). Relevant only in that flipping them renames components, so pin them for stable diffs. |
| `suppress_collision_warning` | `plumbing.py:793-797` | **No** — no public decorator; requires `from drf_spectacular.drainage import set_override` | Do not use. It suppresses the warning without fixing the wrong schema. |

---

## 4. Question 2 — operation IDs

### 4.1 Default derivation

```python
# openapi.py:451-473 (verbatim)
def get_operation_id(self) -> str:
    """ override this for custom behaviour """
    tokenized_path = self._tokenize_path()
    # replace dashes as they can be problematic later in code generation
    tokenized_path = [t.replace('-', '_') for t in tokenized_path]

    if self.method == 'GET' and self._is_list_view():
        action = 'list'
    else:
        action = self.method_mapping[self.method.lower()]

    if not tokenized_path:
        tokenized_path.append('root')

    if re.search(r'<drf_format_suffix\w*:\w+>', self.path_regex):
        tokenized_path.append('formatted')

    if spectacular_settings.OPERATION_ID_METHOD_POSITION == 'PRE':
        return '_'.join([action] + tokenized_path)
    elif spectacular_settings.OPERATION_ID_METHOD_POSITION == 'POST':
        return '_'.join(tokenized_path + [action])
```

`_tokenize_path` (`openapi.py:479-491`) strips `path_prefix` (regex, case-insensitive), drops `{var}`
segments, splits on `/`. `method_mapping` is `{get: retrieve, post: create, put: update, patch:
partial_update, delete: destroy}` (`openapi.py:54-60`). Default
`OPERATION_ID_METHOD_POSITION: 'POST'` (`settings.py:149`) → `payments_list`, `payments_retrieve`,
`payments_create`, `payments_partial_update`, `payments_destroy`. `CAMELIZE_NAMES: True`
(`settings.py:144`) post-processes to `paymentsList` (`plumbing.py:1267-1280`).

**operationIds are derived from the path, not from the view class.** This is the key fact for the
next question.

### 4.2 Same viewset mounted under `/api/v1/` and `/api/v2/` in one document

Neither a silent overwrite nor an error — it depends entirely on whether the version segment survives
tokenisation:

- **Version segment survives** (e.g. `SCHEMA_PATH_PREFIX = r'/api'`): tokens are `['v1','payments']`
  and `['v2','payments']` → `v1_payments_list` and `v2_payments_list`. Distinct, no warning. This is
  the upstream-tested case: `tests/test_view.py:46-53,169-174` mounts the *same* `pi` view at
  `/api/v1/pi/` and `/api/v2/pi/`, generates one combined document, asserts both paths are present —
  under the `no_warnings` fixture.
- **Version segment stripped** (e.g. `SCHEMA_PATH_PREFIX = r'/api/v[0-9]'`): both become
  `payments_list`. Spectacular detects this at the very end of generation:

```python
# plumbing.py:1239-1253 (verbatim)
def sanitize_result_object(result):
    # warn about and resolve operationId collisions with suffixes
    operations = defaultdict(list)
    for path, methods in result['paths'].items():
        for method, operation in methods.items():
            operations[operation['operationId']].append((path, method))
    for operation_id, paths in operations.items():
        if len(paths) == 1:
            continue
        warn(f'operationId "{operation_id}" has collisions {paths}. resolving with numeral suffixes.')
        for idx, (path, method) in enumerate(sorted(paths)[1:], start=2):
            suffix = str(idx) if spectacular_settings.CAMELIZE_NAMES else f'_{idx}'
            result['paths'][path][method]['operationId'] += suffix
```

So: **a warning plus deterministic `_2` / `_3` suffixes**, assigned by `sorted(paths)` order.
Upstream test: `tests/test_warnings.py:247-262` asserts `pi_retrieve` / `pi_retrieve_2` and the
collision message. Two consequences for apiver: (i) nothing is silently lost — the operations remain
distinct; (ii) but the suffix is positional, so inserting a new colliding path can *reassign* which
operation is `_2`. Another reason to never let operationIds collide in the first place.

Also relevant: paths themselves cannot collide, because `EndpointEnumerator` deduplicates on
`(path, method)` before generation (`generators.py:31-36`) — two mounts at different paths are two
entries; the same view reachable twice at the *same* path is collapsed to one.

### 4.3 Supported hooks to namespace operationIds per version

| Hook | Verdict |
|---|---|
| `@extend_schema(operation_id='v2_payments_list')` on a **method** (`utils.py:348,459-462`) | Works, per-method. Note `is_in_scope` also honours `versions=[…]` (`utils.py:437-444`), so one decorator can carry per-DRF-version IDs. Verbose. |
| `@extend_schema(operation_id=…)` on a **class** | **Explicitly rejected**: *"using @extend_schema on viewset class … with parameters operation_id or operation will most likely result in a broken schema"* (`utils.py:529-536`), emitted as an `error()`. Use `@extend_schema_view(list=extend_schema(operation_id=…), …)` instead (`utils.py:642-656`). |
| Subclass `AutoSchema`, override `get_operation_id()` (`openapi.py:451`, *"override this for custom behaviour"*) | **Cleanest.** `self.path` / `self.path_regex` are available (`openapi.py:71-72`), so the version prefix is readable from the path. Install via DRF's `DEFAULT_SCHEMA_CLASS`, or per-view `schema = …`. |
| A `POSTPROCESSING_HOOKS` entry rewriting `result['paths'][…]['operationId']` (`settings.py:98-102`) | **Also excellent, and better than it looks**: hooks run *before* `sanitize_result_object` (`generators.py:292-295`), so a namespacing hook prevents the `_2` suffixes, and any collision it fails to fix is still caught and warned about afterwards. Signature: `hook(result, generator, request, public)`. |
| `OpenApiViewExtension` (`generators.py:131-146`) | Wrong tool — it replaces the *view class* during generation. Use it for third-party views you cannot edit, not for ID naming. |

---

## 5. Question 4 — serving several documents and UIs from one project

Yes, cleanly. Three facts make it work:

1. The three UI views are all `@extend_schema(exclude=True)` (`views.py:132`, `views.py:202`,
   `views.py:244`), so Swagger/Redoc endpoints never appear in any schema.
2. `SpectacularAPIView` itself **is** included by default —
   `SERVE_INCLUDE_SCHEMA: True` (`settings.py:57`) switches between
   `{'responses': {200: OpenApiTypes.OBJECT}}` and `{'exclude': True}` at *import time*
   (`views.py:26-36`). Set it to `False` project-wide so `/api/vN/schema/` is not itself part of the
   diffable surface.
3. The UI views resolve their schema URL via `reverse(self.url_name)` with `url_name = 'schema'` by
   default (`views.py:126,158-164` and `views.py:239,270-276`), and accept an explicit `url` override.
   Per-version UIs therefore need per-version `url_name`s.

### Working wiring sketch

```python
# myproj/api/v1/urls.py   (apiver-generated)
urlpatterns = router_v1.urls          # 'payments/', 'payments/<pk>/', ...

# myproj/api/v2/urls.py   (apiver-generated)
urlpatterns = router_v2.urls

# myproj/urls.py
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView,
)
from myproj.api.v1 import urls as v1_urls
from myproj.api.v2 import urls as v2_urls

# NOTE: EndpointEnumerator walks these with prefix='' (generators.py:51-78), so each
# list must carry the full path as mounted from the project root.
V1_MOUNT    = [path('api/v1/',     include((v1_urls.urlpatterns, 'v1')))]
V2_MOUNT    = [path('api/v2/',     include((v2_urls.urlpatterns, 'v2')))]
ALIAS_MOUNT = [path('api/stable/', include((v2_urls.urlpatterns, 'stable')))]   # alias -> v2

def version_schema(mount, title, version, prefix):
    return SpectacularAPIView.as_view(
        urlconf=mount,                 # views.py:58,66-77 -> only this subtree is enumerated
        custom_settings={              # views.py:79 -> settings.py:282-292
            'TITLE': title,
            'VERSION': version,
            'SCHEMA_PATH_PREFIX': prefix,   # pin it; never rely on auto-estimation
        },
    )

urlpatterns = [
    *V1_MOUNT, *V2_MOUNT, *ALIAS_MOUNT,

    path('api/v1/schema/', version_schema(V1_MOUNT, 'Acme API', '1.0.0', r'/api/v1'),
         name='schema-v1'),
    path('api/v1/docs/',  SpectacularSwaggerView.as_view(url_name='schema-v1'), name='docs-v1'),
    path('api/v1/redoc/', SpectacularRedocView.as_view(url_name='schema-v1'),   name='redoc-v1'),

    path('api/v2/schema/', version_schema(V2_MOUNT, 'Acme API', '2.0.0', r'/api/v2'),
         name='schema-v2'),
    path('api/v2/docs/',  SpectacularSwaggerView.as_view(url_name='schema-v2'), name='docs-v2'),
    path('api/v2/redoc/', SpectacularRedocView.as_view(url_name='schema-v2'),   name='redoc-v2'),
]
```

```python
# settings.py
SPECTACULAR_SETTINGS = {
    'SERVE_INCLUDE_SCHEMA': False,   # keep /schema/ out of the schema      (settings.py:57)
    'COMPONENT_SPLIT_REQUEST': False,  # pin: flipping renames components   (settings.py:36)
    'COMPONENT_SPLIT_PATCH': True,     # pin                                (settings.py:32)
    'SORT_OPERATIONS': True,           # deterministic ordering             (settings.py:114)
}
REST_FRAMEWORK = {'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema'}
```

Caveats, all cited above: `custom_settings` is not thread-safe (`docs/faq.rst:337`); `SERVE_*` keys
are rejected inside it (`settings.py:257-262`); and the mount lists must be the *project-root* paths.

For the CLI, `--urlconf` needs a module, so apiver would generate (or ship) something like
`myproj/schema_urls/v2.py` containing `urlpatterns = V2_MOUNT`, then:

```bash
./manage.py spectacular --urlconf myproj.schema_urls.v2 \
    --custom-settings myproj.schema_urls.V2_SETTINGS \
    --file build/schema-v2.yaml --validate --fail-on-warn
```

(`management/commands/spectacular.py:40-43,81-87,119-134`.) `--fail-on-warn` is what turns the
silent-wrong-schema failure of §3.2 into a build error.

---

## 6. Question 5 — aliases (`/api/stable/` mounting the same router as `/api/v2/`)

### What actually happens if the alias is in scope

`EndpointEnumerator._get_api_endpoints` walks `URLResolver`s recursively, accumulating the prefix
(`generators.py:51-78`); the deduplication step keys on `(path, method)` (`generators.py:31-36`).
Since `/api/v2/payments/` and `/api/stable/payments/` are *different paths*, **both survive**. Then:

- **Paths:** every operation appears twice. The document doubles in size.
- **operationIds:** determined by `_tokenize_path` after prefix stripping. With
  `SCHEMA_PATH_PREFIX = r'/api'`, you get `v2_payments_list` and `stable_payments_list` — distinct,
  **no warning**, which is arguably worse than a collision because nothing tells you the alias
  leaked. With a prefix that strips both segments, you get `payments_list` /
  `payments_list_2` plus the collision warning (`plumbing.py:1248`).
- **Components:** unaffected — the same serializer class resolves to the same name and the same
  identity, so the second lookup is a registry hit (`openapi.py:1696-1697`) with no warning
  (`plumbing.py:797` compares `query_id != registry_id`, and here they are equal).
- **Tags:** with prefix `/api`, the alias operations are tagged `stable`, giving Swagger UI a
  duplicate section.

So the failure mode is **silent duplication**, not corruption. There is no built-in
"this mount is an alias" concept anywhere in drf-spectacular — grepping the source for alias handling
finds nothing.

### The supported ways to exclude a mount

| Mechanism | Works? | Notes |
|---|---|---|
| **`urlconf=<list without the alias mount>`** on the per-version `SpectacularAPIView` (`views.py:58,66-77`) | **Yes — the right answer.** | Costs nothing, is upstream-tested (`tests/test_view.py:27-45`), and needs no hooks. The alias simply isn't in the enumerated subtree. |
| `SpectacularSettings.SERVE_URLCONF` (`settings.py:53`, `views.py:58`) | Partially | Only sets the *global default* for that attribute; one value for the whole project. Useful if there is exactly one schema, useless for per-version. Cannot be set via `custom_settings` (`settings.py:257-262`). |
| A `PREPROCESSING_HOOKS` entry (`settings.py:104-108`, invoked `generators.py:28-29`) | **Yes** | Signature `result = hook(endpoints=result)` where each entry is `(path, path_regex, method, callback)`. Model it on the shipped `preprocess_exclude_path_format` (`hooks.py:201-211`). This is the supported route when the schema must be generated from the *whole* URLconf. Sketch: <br>`def drop_alias_mounts(endpoints, **kwargs): return [e for e in endpoints if not e[0].startswith('/api/stable/')]` |
| `@extend_schema(exclude=True)` (`utils.py:358,454-457`) | **No** | It is attached to the view/method, and `is_excluded()` returns the same answer regardless of which mount produced the operation. It would remove the endpoint from *both* `/api/v2/` and `/api/stable/`. |
| Custom `AutoSchema.is_excluded()` (`openapi.py:125-127`, *"override this for custom behaviour"*) | Yes | Unlike the decorator, the instance has `self.path` (`openapi.py:71`), so it can exclude by mount. Heavier than a preprocessing hook and relies on the undocumented `self.path` attribute. |

**Recommendation for apiver:** aliases should be resolved at wiring time, not schema time — build the
per-version `urlconf` list from the canonical mounts only, and additionally register a
`PREPROCESSING_HOOKS` entry generated from the manifest's alias table as a belt-and-braces measure for
projects that serve one whole-project schema. Whether aliases appear in *any* schema is listed as an
open question in `map.md` ("Alias and gating semantics in detail"); the technical answer is that
including them is possible but only produces duplicate operations, never a merged/"aliased" view —
OpenAPI has no vocabulary for "this path is an alias of that one".

---

## 7. Question 6 — non-viewset views (the depth boundary)

### What is inferred, and what is guessed

`_get_serializer` (`openapi.py:1249-1283`) is the whole story:

```python
# openapi.py:1259-1273 (verbatim)
elif isinstance(view, APIView):
    # APIView does not implement the required interface, but be lenient and make
    # good guesses before giving up and emitting a warning.
    if callable(getattr(view, 'get_serializer', None)):
        return view.get_serializer(context=context)
    elif callable(getattr(view, 'get_serializer_class', None)):
        return view.get_serializer_class()(context=context)
    elif hasattr(view, 'serializer_class'):
        return view.serializer_class
    else:
        error(
            'unable to guess serializer. This is graceful fallback handling for APIViews. '
            'Consider using GenericAPIView as view base class, if view is under your control. '
            'Either way you may want to add a serializer_class (or method). Ignoring view for now.'
        )
```

Confirmed by the docs: *"Introspection heavily relies on those two attributes [`queryset`,
`serializer_class`]. … You can also set those on `APIView`. Even though this is not supported by DRF,
drf-spectacular will pick them up and use them."* (`docs/customization.rst:14-21`), and *"Many
libraries use `@api_view` or `APIView` instead of `ViewSet` or `GenericAPIView`. In those cases,
introspection has very little to work with."* (`docs/customization.rst:185-188`).

For a **bare `APIView` / `@api_view` with no `serializer_class`**, the resulting operation contains:

| Element | Result | Citation |
|---|---|---|
| path & method | Correct — enumeration is URLconf-driven | `generators.py:51-78` |
| `operationId` | Correct — derived from the path, not the view | `openapi.py:451-473` |
| tags | Correct — first path token | `openapi.py:380-384` |
| path parameters | Typed if the Django converter is typed (`<int:pk>`) or the regex is analysable; otherwise `string` **plus a warning** (*"could not derive type of path parameter … Defaulting to 'string'"*) | `openapi.py:493-515` |
| request body | Nothing resolvable → omitted (`if not content: return None`) | `openapi.py:1341-1381` |
| response body | `{'200': {…free-form object…}}` **plus a warning** (*"could not resolve … Defaulting to generic free-form object"*), described as *"Unspecified response body"* | `openapi.py:1464-1472` |
| pagination / filter params | None — `_is_list_view()` and the paginator/filter lookups all need `GenericAPIView` | `openapi.py:129-160,545-573` |
| description | View/handler docstring, unless `DISABLE_DOCSTRING_DESCRIPTIONS` | `settings.py:129-132` |
| auth | From `authentication_classes` (works on any `APIView`) | `openapi.py:~340-370` |

Anything not derived from `APIView` or a subclass is dropped outright with
*"Using not supported View class. Class must be derived from APIView …"* (`generators.py:148-157`).

### Implication for the `diff`/`check` depth boundary (map.md line 22)

The boundary is **sharper and more usable than "we can't say anything"**. For an un-annotated
`APIView`, generated schemas still carry: path, method, operationId, tags, path-parameter names,
auth, and a placeholder 200. So `diff` can reliably detect **route-level** breakage on bare APIViews —
removed endpoint, removed method, renamed/retyped path parameter, changed auth — and reliably detect
**nothing** about request/response payloads, because both sides are the same free-form
`{"type": "object"}`. Two practical consequences:

- apiver's `check` should treat "spectacular emitted a warning for this operation" as a first-class
  signal, i.e. report `N operations have unresolved payloads; payload-level checks skipped for them`
  rather than silently reporting "no breaking changes". Warnings are printed to stderr and counted
  (`drainage.py:77-99`), and `--fail-on-warn` (`management/commands/spectacular.py:55-61`) already
  exists to gate on them; a `POSTPROCESSING_HOOKS` entry could also stamp an `x-apiver-unresolved`
  extension onto such operations for machine consumption.
- The documented remedy is cheap and worth putting in apiver's docs: add `serializer_class` (or
  `@extend_schema(request=…, responses=…)`) to the APIView, or supply an `OpenApiViewExtension`
  (`docs/customization.rst:185-200`, `generators.py:131-146`) — both promote the view to full depth
  without changing runtime behaviour.

---

## 8. Question 7 — schema-diffing prior art

### 8.1 Comparison table

| Tool | Language | Licence | Maturity | Latest release | Breaking vs non-breaking? | Callable from a Python CLI? |
|---|---|---|---|---|---|---|
| **[oasdiff](https://github.com/oasdiff/oasdiff)** | Go | Apache-2.0 | ★1,308; created 2021-02-10; active (pushed 2026-08-09) | **v1.28.0, 2026-08-06** | **Yes, best in class.** `breaking` = ERR+WARN only; `changelog` = all levels; `diff` = every difference incl. docs-only. Three severities `ERR`/`WARN`/`INFO`, per-check severity customisable. The `en` message catalogue contains **505 `*-description` entries** (`checker/localizations_src/en/messages.yaml`), consistent with the project's "509 distinct changes" claim. | **Yes, via subprocess.** No PyPI package (`pypi.org/pypi/oasdiff/json` → 404). Ship as: Docker (`tufin/oasdiff`), `install.sh` to `/usr/local/bin`, brew, `go install`, or pre-built binaries for macOS/Linux/Windows × x86_64/arm64. `--format json|yaml|junit|githubactions|markdown|html`, `oasdiff schema` prints a JSON Schema for the JSON output, `--fail-on ERR|WARN|INFO` sets exit code 1. |
| **[openapi-changes](https://github.com/pb33f/openapi-changes)** | Go (repo tagged JavaScript for the report bundle) | Apache-2.0 | ★359; active (pushed 2026-07-01) | v0.2.10, 2026-07-01 | Yes — classifies breaking vs non-breaking over two specs *or* over git history. Built on `libopenapi`'s `what-changed` model. Supports OpenAPI 3.0/3.1/3.2. | Yes, via subprocess. Not on PyPI; distributed via brew, **npm (`@pb33f/openapi-changes`)**, Docker, `install.sh`, `go build`. `report` emits JSON; `summary` is the CI command; per the docs, *"Use `--error-on-diff` if any detected change should produce a non-zero exit code"* — note that is *any* change, not *breaking* changes, so gating on breaking-only needs parsing the JSON report. |
| **[OpenAPITools/openapi-diff](https://github.com/OpenAPITools/openapi-diff)** | Java (needs a JRE) | Apache-2.0 | ★1,095; active (pushed 2026-08-05) | 2.1.7, 2026-01-26 | Yes — `--fail-on-incompatible` (breaking only) vs `--fail-on-changed` (any change); `--state` prints `no_changes\|incompatible\|compatible`. | Awkward. Subprocess a JAR/brew binary or `docker run openapitools/openapi-diff`. A JRE dependency is a much bigger ask than a static Go binary. OpenAPI 3.0 only per README ("Supports OpenAPI spec v3.0"); 3.1 is not claimed. |
| **[Azure/openapi-diff](https://github.com/Azure/openapi-diff)** (`oad`) | C#/Node | MIT | ★288; active (pushed 2026-08-07) | (npm `oad`) | Yes, but rule set is tuned to Azure's ARM spec conventions. | npm-installed. Not a good general fit. |
| **[Optic](https://github.com/opticdev/optic)** | TypeScript | MIT | ★1,535 — **ARCHIVED 2026-01-08** | — | Was yes | **Do not depend on it.** Dead. |
| **[Yelp/swagger-spec-compatibility](https://github.com/Yelp/swagger-spec-compatibility)** | **Python** | MIT (PyPI classifier) / Apache-2.0 (repo) | ★20; last real commit 2022-12-16 (the 2026-04-02 commit is a CI workflow); last PyPI release **1.3.4, 2021-08-20**; classifiers stop at Python 3.7 | 1.3.4 (2021) | Yes, rule-based, but *"not supposed to cover all the possible cases of backward incompatibility"* (its own README) | pip-installable — and **useless here**: it handles *"Swagger/OpenAPI 2.0 specification"* only, while spectacular emits OpenAPI 3.0.3/3.1.0 (`settings.py:47-50`). Depends on `bravado`/`bravado-core`. |
| **[civisanalytics/swagger-diff](https://github.com/civisanalytics/swagger-diff)** | Ruby | BSD-3 | ★272; last push 2023-03-23 | — | Yes (Swagger 2.0) | No. Dead + wrong spec version. |

Also checked and **not found on PyPI** (all HTTP 404 on `pypi.org/pypi/<name>/json`, 2026-08-09):
`oasdiff`, `oasdiff-py`, `oasdiff-python`, `openapi-diff`, `openapi-diff-py`, `openapi3-diff`,
`openapi-changes`, `openapi-spec-diff`, `openapi-compare`, `openapi-checker`,
`openapi-breaking-changes`, `apidiff`, `oad`.

### 8.2 Conclusion for apiver

**There is no maintained Python-native OpenAPI 3 breaking-change engine. There is one clearly
dominant tool, and it is a single static Go binary.**

`oasdiff` is the right dependency, and it happens to be built for apiver's exact situation:

```
# docs/PATH-PREFIX.md (verbatim)
# Path Prefix Modification
Sometimes paths prefixes need to be modified, for example, to create a new version:
- /api/v1/...
- /api/v2/...
...
oasdiff diff original.yaml new.yaml --strip-prefix-base /api/v1 --strip-prefix-revision /api/v2
```

That is `apiver diff v1 v2` in one flag pair. Combined with per-version documents whose operationIds
are already version-stripped (§2.2), base and revision align on both path and operationId with no
pre-processing at all. Other directly relevant oasdiff features: endpoint matching that survives
renamed path parameters (`docs/MATCHING-ENDPOINTS.md`), `allOf` flattening
(`docs/ALLOF.md`), deprecation/sunset awareness (`docs/DEPRECATION.md` — apiver already has
Deprecation/Sunset headers in 0.1 scope), stability levels (`docs/STABILITY.md`), and "breaking change
released without a major version bump" (`docs/VERSIONING.md`).

Integration options, cheapest first:

1. **Optional external binary.** `apiver diff` shells out to `oasdiff` if it is on `PATH`, otherwise
   prints an install hint. Zero packaging cost; the failure mode is a clear error, not a wrong answer.
2. **Docker fallback** (`docker run --rm -t tufin/oasdiff …`) for CI users without the binary.
3. **Vendored binary wheels** — build platform wheels that bundle the Go binary (the `ruff`/`ripgrep`
   pattern). Realistic, but it makes apiver a multi-platform binary publisher, which is a large
   step up from a pure-Python sdist. Not for 0.2.
4. **Write it ourselves.** Only worth it for the narrow subset apiver can guarantee (paths, methods,
   operationIds, required-ness, enum values, component field sets). oasdiff's ~505 checks are the
   argument against.

One governance note to carry into the decision: oasdiff's docs now foreground a commercial hosted
product (`oasdiff.com`, "oasdiff Pro") alongside the CLI, and the repo moved from `Tufin/oasdiff` to
`oasdiff/oasdiff` (GitHub redirects the old path). The CLI itself is Apache-2.0 with all `breaking`/
`changelog`/`diff` commands in-repo, and `--open` (the only feature that talks to their servers) is
opt-in. Pin a version and re-check licence terms before shipping, but there is no evidence of an
open-core split in the diffing engine today.

---

## 9. Summary of behaviours apiver must design around

| Situation | drf-spectacular's actual behaviour | Evidence |
|---|---|---|
| Two versions as two documents | Independent registries; no interaction of any kind | `generators.py:107` |
| Same viewset at two mounts, version token kept | Two operations, distinct IDs, no warning | `generators.py:31-36`, `openapi.py:479-491`; `tests/test_view.py:169-174` |
| Same viewset at two mounts, version token stripped | Warning + `_2` suffix, positional | `plumbing.py:1239-1253`; `tests/test_warnings.py:247-262` |
| Two *different* classes with the same name | Warning; **second class never mapped; refs point at the first** | `plumbing.py:797-802`, `openapi.py:1696-1697`; `tests/test_warnings.py:22-49` |
| `PaymentV2Serializer(PaymentV1Serializer)`, neither decorated | `PaymentV2` / `PaymentV1`; both fully spelled out; no `allOf` | `openapi.py:1637-1639` |
| Same, but V1 carries `@extend_schema_serializer(...)` | V2 **inherits** V1's `component_name` → collision | `drainage.py:153-177` **[probe]** |
| `SCHEMA_PATH_PREFIX` left at `None` | Prefix = `commonpath` of this document's paths → operationIds change when endpoints are added/removed | `generators.py:210-220` |
| Bare `APIView`, no `serializer_class` | Error + warning; free-form 200 body; route metadata still correct | `openapi.py:1269-1273,1464-1472` |
| Alias mount left in scope | Silent duplication of every operation | `generators.py:31-78` |

---

## 10. Not supported / requires private API

Explicit list of everything apiver would have to reach past the public API for, or build itself.

**Requires reaching past the documented API (works, but unsupported surface):**

1. **`self.path` / `self.path_regex` inside a custom `AutoSchema`.** Overriding
   `get_operation_id()`, `get_serializer_name()` or `is_excluded()` per version means reading the
   operation's path. Those attributes are set in `get_operation` (`openapi.py:71-74`) and are stable
   across the codebase, but they are instance state, not a documented contract. The methods
   themselves *are* sanctioned (`"""override this for custom behaviour"""`) and
   `drf_spectacular.openapi` is in `docs/drf_spectacular.rst`. **Mitigation:**
   `OpenApiSerializerExtension.get_name(auto_schema, direction)` (`extensions.py:67-69`) receives
   `auto_schema` *as a documented parameter*, so component renaming can be done entirely within
   documented surface; only operationId renaming needs the instance attribute (or a
   `POSTPROCESSING_HOOKS` entry, which is fully public and gets the finished `paths` dict).
2. **`drf_spectacular.generators.SchemaGenerator` used directly in-process.** Referenced by the
   `DEFAULT_GENERATOR_CLASS` setting and `--generator-class`, so it is an extension point, but the
   module is absent from the published API reference and its `__init__`/`get_schema`/`parse`
   signatures are not documented.
3. **`drf_spectacular.drainage` (`set_override` / `get_override` / `warn`).** Not in the API
   reference. Needed only for `suppress_collision_warning` (`plumbing.py:793-797`) — which apiver
   should not use anyway, since it hides a wrong schema rather than fixing it.
4. **`drf_spectacular.plumbing` in its entirety.** Named "plumbing", not exported, not documented.
   `ComponentRegistry`, `ResolvedComponent`, `sanitize_result_object` are all internal. apiver must
   not import from it.

**Not supported at all — apiver must build it:**

5. **Any notion of a URL mount being an alias of another.** No setting, no hook parameter, nothing.
   Aliases are handled by *not enumerating them* (per-version `urlconf`) or by a hand-written
   `PREPROCESSING_HOOKS` filter. There is no way to make one operation appear under two paths without
   duplicating it, and no OpenAPI vocabulary for it either.
6. **Per-mount exclusion via `@extend_schema(exclude=True)`.** The decorator is view-scoped;
   `is_in_scope` filters by method and DRF *version*, never by path (`utils.py:437-444`). Excluding
   one mount of a multiply-mounted view requires a preprocessing hook or a custom
   `AutoSchema.is_excluded()`.
7. **Automatic version-aware component naming.** Nothing infers "these two components are the same
   resource at two versions". Every naming scheme is apiver's to define and apply consistently.
8. **Any inheritance relationship in the emitted schema.** Spectacular flattens serializers; a V2
   component will not be expressed as `allOf: [PaymentV1, {…delta…}]`. If apiver wants the *delta*
   visible in the schema, it must synthesise it — nothing upstream will.
9. **Inheritance-safe `@extend_schema_serializer`.** There is no "do not inherit this annotation"
   flag. apiver must either re-decorate every subclass, or avoid the decorator entirely in favour of
   a naming rule in a custom `AutoSchema`.
10. **Deterministic operationIds without pinning `SCHEMA_PATH_PREFIX`.** The auto-estimator is
    content-dependent by design (`generators.py:210-220`). There is no "stable IDs" mode.
11. **Thread-safe per-request `custom_settings`.** Documented as not thread-safe
    (`docs/faq.rst:337`). If apiver serves per-version docs under load with differing settings, this
    is a real hazard; the alternative is putting the differing values in per-version
    `SpectacularAPIView` subclasses only where dedicated attributes exist (`urlconf`, `api_version`,
    `patterns`, `serve_public`, `generator_class`) — `SCHEMA_PATH_PREFIX` and `TITLE` have no
    dedicated attribute, so they can only come from `custom_settings` or a custom generator class.
12. **A `--patterns` option on `./manage.py spectacular`.** Only `--urlconf <dotted module>` exists
    (`management/commands/spectacular.py:40-43`), so offline per-version generation needs a real
    module per version, or apiver's own management command / in-process generator call.

**Unverifiable from source or docs (stated as such rather than guessed):**

13. Whether generating several schemas sequentially in one process leaks state between them beyond
    the settings patching. Each `SchemaGenerator` builds a fresh `ComponentRegistry`
    (`generators.py:107`) and `get_schema` calls `reset_generator_stats()` (`generators.py:285`), and
    `create_view` explicitly restores `callback.cls` after an `OpenApiViewExtension` swap
    (`generators.py:141-146`) — so the design intent is clearly "re-runnable". But no upstream test
    generates two documents in one process and asserts independence, and this report ran no Django,
    so I cannot claim it is verified.
14. The exact behaviour of `openapi-changes --error-on-diff` with respect to *breaking-only* gating.
    The docs sentence quoted above covers "any detected change"; whether a breaking-only exit code
    exists was not established from primary sources.
