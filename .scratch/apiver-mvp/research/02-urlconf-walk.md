# 02 — URLconf walk: what is actually recoverable?

Research report for ticket [02-urlconf-walk-feasibility](../issues/02-urlconf-walk-feasibility.md).

**Sources read (all primary, pinned):**

| Project | Version | How verified |
|---|---|---|
| Django | **6.1** (released 2026-08-05) | `https://pypi.org/pypi/django/json`; source read at tag `6.1`, `django/__init__.py` → `VERSION = (6, 1, 0, "final", 0)` |
| Django REST Framework | **3.18.0** (released 2026-08-07) | `https://pypi.org/pypi/djangorestframework/json`; source read at tag `3.18.0`, `rest_framework/__init__.py` → `__version__ = '3.18.0'` |
| drf-spectacular | **0.30.0** (released 2026-07-06) | `https://pypi.org/pypi/drf-spectacular/json`; source read at tag `0.30.0` |

All line numbers below refer to those tags. Raw file URLs follow the pattern
`https://raw.githubusercontent.com/<org>/<repo>/<tag>/<path>`.

Nothing was installed and no Django code was executed. Four pure-CPython (stdlib-only, 3.13.5) probes
were run to confirm language-level behaviour of `type()`, `functools.wraps`, `functools.partial`,
`functools.update_wrapper` and `inspect`; these are marked **[probe]** and are stdlib semantics, not
Django behaviour.

---

## 1. Bottom line

**Yes — `apiver migrate` as "walk the URLconf, generate one wiring file, move nothing" is feasible,
and the mechanism is load-bearing in production code today.** Every DRF view callable that reaches a
URLconf carries a hard reference back to its class: `APIView.as_view()` sets `view.cls` and
`view.initkwargs` (`rest_framework/views.py:140-141`), `ViewSetMixin.as_view()` sets `view.cls`,
`view.initkwargs` *and* `view.actions` (`rest_framework/viewsets.py:136-138`), and Django's own
`View.as_view()` sets the documented-public `view.view_class` / `view.view_initkwargs`
(`django/views/generic/base.py:107-108`). Crucially for router-registered viewsets, DRF's
`SimpleRouter.get_urls()` injects `basename` and `detail` *into the initkwargs*
(`rest_framework/routers.py:301-305`), so **prefix, basename and the detail/list distinction are all
recoverable from the URLPattern alone — the router object is never needed.** Three caveats set the
shape of the implementation. First, **drf-spectacular's `EndpointEnumerator` is not reusable as-is**:
it is a *schema* enumerator, and it deliberately drops everything that is not a DRF view
(`rest_framework/schemas/generators.py:26-33, 117-118`), everything with `schema = None`, and every
`.{format}` route — apiver needs its own walk that borrows the traversal shape but none of the
filtering. Second, **the attributes apiver depends on are undocumented on the DRF side**: `.cls` and
`.initkwargs` appear nowhere in DRF's docs (grepped `docs/api-guide/views.md`, `viewsets.md`,
`routers.md`, `generic-views.md`, `schemas.md`, `topics/browsable-api.md` at 3.18.0 — zero hits) and
their source docstring says only "Used for breadcrumb generation"; they are de-facto public because
DRF's own schema generator, the browsable API, drf-spectacular and drf-yasg all depend on them, but
they are a private-API bet and should be pinned in a DRF-version support matrix. Third, **discovery ≠
regeneration**: a route can be perfectly discoverable and still have no importable symbol to name in
the generated file (closure-built classes, unreconstructable `initkwargs`, non-`wraps` decorators).
The correct posture is therefore *generate, then verify by re-walking the generated registry and
diffing absolute paths against the discovered set* — and hard-fail with a named diagnostic on
anything in the "cannot be recovered" list rather than emitting a file that silently drops routes.

---

## 2. Recoverability table

Legend: **Y** = recoverable directly from the `URLPattern`; **Y\*** = recoverable with a documented
caveat (see notes); **D** = derivable by string/heuristic work on the route; **N** = not recoverable.

| View type | callback → class | mount path (absolute) | router prefix (local) | basename | detail/list | serializer_class | permission_classes | queryset | source file | importable symbol to re-emit |
|---|---|---|---|---|---|---|---|---|---|---|
| **Router-registered ViewSet** (`SimpleRouter`/`DefaultRouter`) | **Y** `callback.cls` <sup>[a]</sup> | **Y** concat of `str(p.pattern)` | **D** <sup>[b]</sup> | **Y** `callback.initkwargs['basename']` <sup>[c]</sup> | **Y** `callback.initkwargs['detail']` (bool) <sup>[c]</sup> | **Y\*** `cls.serializer_class` <sup>[d]</sup> | **Y\*** `cls.permission_classes` <sup>[e]</sup> | **Y\*** `cls.queryset` — **must not evaluate** <sup>[f]</sup> | **Y** `inspect.getsourcefile(cls)` | **Y** the *class* (not the view fn) <sup>[g]</sup> |
| **ViewSet mounted by hand** `VS.as_view({'get':'list'})` | **Y** `callback.cls` | **Y** | n/a | **N** unless passed explicitly <sup>[h]</sup> | **N** unless passed explicitly <sup>[h]</sup> | **Y\*** | **Y\*** | **Y\*** | **Y** | **Y** the class + the `actions` dict from `callback.actions` |
| **APIView / GenericAPIView subclass** | **Y** `callback.cls` **and** `callback.view_class` (same object) | **Y** | n/a | n/a | **D** heuristic only <sup>[i]</sup> | **Y\*** | **Y\*** | **Y\*** | **Y** | **Y** the class |
| **`@api_view` function view** | **Y** `callback.cls` → a *synthetic* `WrappedAPIView` <sup>[j]</sup> | **Y** | n/a | n/a | **D** heuristic only | **Y\*** only if the func set it | **Y\*** copied from func at decoration | **N** | **Y\*** file yes, line no <sup>[j]</sup> | **Y\*** import `cls.__name__` from `cls.__module__` — **`__qualname__` is wrong** <sup>[j]</sup> |
| **Plain Django `View` subclass** | **Y** `callback.view_class` (documented) <sup>[k]</sup> | **Y** | n/a | n/a | n/a | **N** | **N** | **N** | **Y** | **Y** the class |
| **`django.views.generic` CBV** (`TemplateView`, `ListView`, …) | **Y** `callback.view_class` + `callback.view_initkwargs` | **Y** | n/a | n/a | n/a | **N** | **N** | **Y\*** `cls.queryset` / `view_initkwargs['queryset']` | **Y** | **Y\*** class yes; `view_initkwargs` only if repr-able <sup>[l]</sup> |
| **Plain function view** `def v(request)` | n/a (it *is* the symbol) | **Y** | n/a | n/a | n/a | **N** | **N** | **N** | **Y** `getsourcefile(callback)` | **Y\*** `__module__`+`__qualname__`, fails on `<locals>`/`<lambda>` |
| **`DefaultRouter` `APIRootView`** | **Y** `callback.cls` | **Y** | n/a | n/a | n/a | **N** | **Y\*** | **N** | **Y** (DRF's own file) | **N** — `initkwargs={'api_root_dict': {...}}` is router-computed <sup>[m]</sup> |

Notes:

- **[a]** `rest_framework/viewsets.py:136-138`. Note `ViewSetMixin.as_view()` **fully reimplements**
  `as_view` and never calls `django.views.generic.base.View.as_view`, so a router callback has `.cls`
  but **no `.view_class`**. Any discovery code that only looks for `view_class` (the common
  Django-land idiom, e.g. `django-extensions show_urls`) misses every viewset. Conversely
  `APIView.as_view()` calls `super().as_view()` (`rest_framework/views.py:139`) so APIView callbacks
  have **both**.
- **[b]** Not stored anywhere; see §3.2. Derivable from the emitted regex, or simply irrelevant —
  apiver is path-keyed, so the absolute path is the identity.
- **[c]** `rest_framework/routers.py:301-305`.
- **[d]** `serializer_class` defaults to `None` on `GenericAPIView`
  (`rest_framework/generics.py`, `queryset = None` / `serializer_class = None`). Views that override
  `get_serializer_class()` expose nothing statically — see §3.3.
- **[e]** Defaults to `api_settings.DEFAULT_PERMISSION_CLASSES` (`rest_framework/views.py:112`), so
  you read the *effective* value and cannot tell declared-on-class from project default.
- **[f]** `APIView.as_view()` monkey-patches `cls.queryset._fetch_all` to raise `RuntimeError`
  (`rest_framework/views.py:130-137`). Reading `.model` is safe; iterating/`bool()` is not.
- **[g]** The router's view callable is created inside `SimpleRouter.get_urls()`
  (`rest_framework/routers.py:307`) and has no module-level name. You regenerate the *registration*
  (`router.register(prefix, ViewSetClass, basename=...)`), not the callable.
- **[h]** `ViewSetMixin.as_view()` defaults `cls.basename = None` and `cls.detail = None`
  (`rest_framework/viewsets.py:75-79`) — see §3.2 for why this is actively hostile to static reads.
- **[i]** Same heuristic drf-spectacular uses; see §3.2 and `drf_spectacular/openapi.py:129-159`.
- **[j]** `rest_framework/decorators.py:25-29, 55-56, 88`.
- **[k]** Documented in `docs/ref/class-based-views/base.txt`: "The returned view has ``view_class``
  and ``view_initkwargs`` attributes."
- **[l]** `django/views/generic/base.py:108`.
- **[m]** `rest_framework/routers.py:373-378`.

---

## 3. Question-by-question

### 3.1 — What does `.callback` give you, and can you recover the class?

`URLPattern.__init__(self, pattern, callback, default_args=None, name=None)` stores the view callable
verbatim as `self.callback` (`django/urls/resolvers.py:422-427`). Django will not let you route a
class: `URLPattern._check_callback` raises system-check error `urls.E009` if `callback` is a `View`
subclass rather than a callable (`django/urls/resolvers.py:449-467`), and `_path()` raises `TypeError`
for a non-callable, non-`include` view (`django/urls/conf.py:80-92`). So `.callback` is always a
function (or other callable).

**Django `View.as_view()` — public and documented:**

```python
# django/views/generic/base.py:107-118
        view.view_class = cls
        view.view_initkwargs = initkwargs

        # __name__ and __qualname__ are intentionally left unchanged as
        # view_class should be used to robustly determine the name of the view
        # instead.
        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        view.__annotations__ = cls.dispatch.__annotations__
        # Copy possible attributes set by decorators, e.g. @csrf_exempt, from
        # the dispatch method.
        view.__dict__.update(cls.dispatch.__dict__)
```

Documented at `docs/ref/class-based-views/base.txt` under `as_view(**initkwargs)`: *"The returned view
has ``view_class`` and ``view_initkwargs`` attributes."* Note the explicit comment that `__name__` /
`__qualname__` on the returned function are **deliberately left as
`View.as_view.<locals>.view`** — do not name views from the callback's qualname; use `view_class`.

**DRF `APIView.as_view()` — sets `cls` and `initkwargs`, undocumented:**

```python
# rest_framework/views.py:122-149
    def as_view(cls, **initkwargs):
        """
        Store the original class on the view function.

        This allows us to discover information about the view when we do URL
        reverse lookups.  Used for breadcrumb generation.
        """
        if isinstance(getattr(cls, 'queryset', None), models.query.QuerySet):
            def force_evaluation():
                raise RuntimeError(
                    'Do not evaluate the `.queryset` attribute directly, '
                    ...
                )
            cls.queryset._fetch_all = force_evaluation

        view = super().as_view(**initkwargs)
        view.cls = cls
        view.initkwargs = initkwargs
        ...
        return csrf_exempt(view)
```

**DRF `ViewSetMixin.as_view()` — sets `cls`, `initkwargs` *and* `actions`:**

```python
# rest_framework/viewsets.py:126-144
        # take name and docstring from class
        update_wrapper(view, cls, updated=())

        # and possible attributes set by decorators
        # like csrf_exempt from dispatch
        update_wrapper(view, cls.dispatch, assigned=())

        # We need to set these on the view function, so that breadcrumb
        # generation can pick out these bits of information from a
        # resolved URL.
        view.cls = cls
        view.initkwargs = initkwargs
        view.actions = actions
        ...
        return csrf_exempt(view)
```

Both DRF paths wrap the result in `csrf_exempt`. That is **not** attribute-destroying:
`django/views/decorators/csrf.py:50-68` returns `wraps(view_func)(_view_wrapper)`, and
`functools.wraps` copies `__dict__` (`WRAPPER_UPDATES = ('__dict__',)`), so `cls`, `initkwargs`,
`actions`, `view_class` and `view_initkwargs` all survive the wrap. **[probe]** confirmed:
`wraps` keeps a custom `cls` attribute; a hand-rolled decorator without `wraps` does not.

Public/private verdict:

| Attribute | Set by | Documented? |
|---|---|---|
| `view_class`, `view_initkwargs` | `django/views/generic/base.py:107-108` | **Yes**, `docs/ref/class-based-views/base.txt` |
| `cls`, `initkwargs` | `rest_framework/views.py:140-141`, `viewsets.py:136-137` | **No** — zero hits across DRF 3.18.0 `docs/`. Docstring says "Used for breadcrumb generation." |
| `actions` | `rest_framework/viewsets.py:138` | **No**. But it is the canonical viewset-vs-APIView discriminator, used by DRF itself (`schemas/generators.py:136`) and drf-spectacular (`generators.py:81`). |

Django itself reads these in `URLPattern.lookup_str` (`django/urls/resolvers.py:487-500`):

```python
    @cached_property
    def lookup_str(self):
        callback = self.callback
        if isinstance(callback, functools.partial):
            callback = callback.func
        if hasattr(callback, "view_class"):
            callback = callback.view_class
        elif not hasattr(callback, "__name__"):
            return callback.__module__ + "." + callback.__class__.__name__
        return callback.__module__ + "." + callback.__qualname__
```

For a **viewset** callback there is no `view_class`, so this falls to the `__qualname__` branch — which
happens to be correct, because `update_wrapper(view, cls, updated=())` copied `__qualname__` off the
class (**[probe]** confirmed: `update_wrapper(fn, SomeClass, updated=())` sets
`fn.__qualname__ == 'SomeClass'`). So `lookup_str` is a usable *fallback* dotted path for both APIViews
and viewsets — but see §5/F2 for the `@api_view` case where it is actively wrong.

### 3.2 — Prefix, basename, detail/list for router-registered viewsets

**You do not need the router object.** `SimpleRouter.get_urls()` bakes the answers into `initkwargs`:

```python
# rest_framework/routers.py:301-309
                initkwargs = route.initkwargs.copy()
                initkwargs.update({
                    'basename': basename,
                    'detail': route.detail,
                })

                view = viewset.as_view(mapping, **initkwargs)
                name = route.name.format(basename=basename)
                ret.append(self._url_conf(regex, view, name=name))
```

Therefore, for every router-produced `URLPattern`:

- **basename** → `callback.initkwargs['basename']`. Also redundantly encoded in `pattern.name`
  (`'{basename}-list'`, `'{basename}-detail'`, `'{basename}-{url_name}'`;
  `rest_framework/routers.py:103, 111, 124, 132`).
- **detail/list** → `callback.initkwargs['detail']` — an actual boolean, not a heuristic. This covers
  `@action(detail=True/False)` routes too, via `DynamicRoute.detail`
  (`rest_framework/routers.py:203-208, 218-224`).
- **action mapping** → `callback.actions`, e.g. `{'get': 'list', 'post': 'create'}`.
- **suffix** → `initkwargs['suffix']` is `'List'` / `'Instance'` for the two standard routes
  (`routers.py:105, 126`); `@action` routes instead get `name` and `description` injected by the
  `@action` decorator (`rest_framework/decorators.py:235-239`).

DRF's own docs corroborate the contract (`docs/api-guide/routers.md:223`): *"the `detail`, `basename`,
and `suffix` arguments are reserved for viewset introspection."*

**Do not read these off the class.** `ViewSetMixin.as_view()` *writes* them onto the class as `None`
every time it is called:

```python
# rest_framework/viewsets.py:66-79
        cls.name = None
        cls.description = None
        cls.suffix = None
        cls.detail = None
        cls.basename = None
```

So after a router has been built, `UserViewSet.basename is None` and `UserViewSet.detail is None`
regardless of registration. The truth lives only in `callback.initkwargs`.

**Prefix.** The router-local prefix is *not* stored anywhere — `prefix` is a loop variable in
`get_urls()` consumed by `route.url.format(prefix=..., lookup=..., trailing_slash=...)`
(`rest_framework/routers.py:272-288`). What you can recover:

- the **absolute mount path**, by concatenating `str(pattern.pattern)` down the resolver tree — exactly
  what DRF's enumerator does (`rest_framework/schemas/generators.py:82`);
- the **router-local prefix**, derivable: group patterns by `(callback.cls, initkwargs['basename'])`,
  find the one whose `pattern.name == f'{basename}-list'`, and strip the trailing slash — its route is
  literally `^{prefix}{trailing_slash}$`. If the viewset implements neither `list` nor `create`, the
  list route is skipped entirely (`routers.py:279-281 → continue`) and you must instead strip the
  lookup regex (`get_lookup_regex`, `routers.py:238-264`) off the detail route;
- **`trailing_slash`**, by whether that route ends in `/`;
- **`use_regex_path`**, by `isinstance(pattern.pattern, RoutePattern)` vs `RegexPattern` — this is a
  3.18-era `SimpleRouter.__init__` option (`routers.py:138-159`).

What you **cannot** recover is the split point between an `include()` prefix and the router prefix:
`/api/users/` is indistinguishable from `include('api.urls')` + `router.register('users', …)` versus
`include('')` + `router.register('api/users', …)`. For a path-keyed library this is a non-issue — the
absolute path is the identity — but it means the generated file must own the whole mount, not try to
reproduce the original file split.

For **non-router** viewsets (`path('x/', VS.as_view({'get': 'list'}))`) there is no `basename` and no
`detail` unless the author passed them; DRF's docs flag exactly this
(`docs/api-guide/viewsets.md:230`): *"the `basename` is provided by the router during ViewSet
registration. If you are not using a router, then you must provide the `basename` argument to the
`.as_view()` method."*

For **APIViews**, detail-vs-list has no ground truth at all. drf-spectacular's answer is an explicitly
labelled guess (`drf_spectacular/openapi.py:129-159`):

```python
    def _is_list_view(self, serializer=None) -> bool:
        """
        partially heuristic approach to determine if a view yields an object or a
        list of objects. used for operationId naming, array building and pagination.
        defaults to False if all introspection fail.
        """
```
…checking, in order: list-serializer, basic type, `view.action == 'list'`, non-GET → False,
`isinstance(view, ListModelMixin)`, and finally whether `lookup_url_kwarg`/`lookup_field` appears in the
path template.

### 3.3 — `serializer_class`, `permission_classes`, `queryset`

All three are ordinary class attributes on `GenericAPIView` (`rest_framework/generics.py`):
`queryset = None`, `serializer_class = None`, `lookup_field = 'pk'`, `lookup_url_kwarg = None`. Reading
`callback.cls.serializer_class` works and is trivially safe. Three qualifications:

1. **Defaults are indistinguishable from declarations.** `APIView` seeds its policy attributes from
   settings at import time (`rest_framework/views.py:106-116`):
   `permission_classes = api_settings.DEFAULT_PERMISSION_CLASSES`, likewise
   `authentication_classes`, `renderer_classes`, `parser_classes`, `throttle_classes`,
   `versioning_class`. So a class that declares nothing still reports the project defaults. You cannot
   tell "declared" from "inherited" without walking `cls.__mro__` / `vars(cls)`.
2. **Dynamic overrides are invisible statically.** A view overriding `get_serializer_class()` or
   `get_queryset()` exposes nothing useful as an attribute. drf-spectacular's answer is to *instantiate
   the view and call the methods*, with layered fallbacks and an error emitted when it gives up
   (`drf_spectacular/openapi.py:1249-1280`):

   ```python
       def _get_serializer(self):
           view = self.view
           context = build_serializer_context(view)
           try:
               if isinstance(view, GenericAPIView):
                   if view.__class__.get_serializer == GenericAPIView.get_serializer:
                       return view.get_serializer_class()(context=context)
                   return view.get_serializer(context=context)
               elif isinstance(view, APIView):
                   ...
                   else:
                       error('unable to guess serializer. This is graceful fallback handling for APIViews. ...')
   ```
   Similarly `get_view_model` prefers `view.queryset.model` and only then risks `get_queryset()`
   (`drf_spectacular/plumbing.py:211-231`), emitting a warning if that raises. Both routes require
   *instantiating* a view, which is what `BaseSchemaGenerator.create_view` exists for
   (`rest_framework/schemas/generators.py:187-208`).
3. **`queryset` is booby-trapped.** `APIView.as_view()` replaces `cls.queryset._fetch_all` with a
   function that raises `RuntimeError` (`rest_framework/views.py:130-137`). Reading the attribute and
   its `.model` is fine; evaluating it is not. `get_view_model` deliberately touches only `.model`.

**For apiver's purposes none of this is on the critical path.** `migrate` generates *wiring*, not
serializer declarations — it needs `cls`, not `cls.serializer_class`. These attributes matter only for
the `diff`/`check` features deferred to 0.2, and there the map's standing decision already applies:
schema reasoning is bounded by what drf-spectacular understands.

### 3.4 — Source file and line

`inspect.getsourcefile(cls)` and `cls.__module__` / `cls.__qualname__` work for any normally-defined
class. drf-spectacular does exactly this, and its defensiveness is instructive
(`drf_spectacular/drainage.py:137-149`):

```python
@functools.lru_cache(maxsize=1000)
def _get_source_location(obj):
    try:
        sourcefile = inspect.getsourcefile(obj)
    except:  # noqa: E722
        sourcefile = None
    try:
        # This is a rather expensive operation. Only do it when explicitly enabled (CLI)
        # and cache results to speed up some recurring objects like serializers.
        lineno = inspect.getsourcelines(obj)[1] if GENERATOR_STATS._trace_lineno else None
    except:  # noqa: E722
        lineno = None
    return sourcefile, lineno
```

Two things to copy: bare-except both calls, and treat `getsourcelines` as opt-in because it is
expensive (it reads and parses the file).

Failure cases, confirmed **[probe]** on CPython 3.13.5:

- A class built by `type('WrappedAPIView', (Base,), {...})` with `__module__` reassigned: 
  `inspect.getsourcefile()` **succeeds** (it resolves `sys.modules[__module__].__file__`), but
  `inspect.getsourcelines()` **raises `OSError`** — there is no `class WrappedAPIView` statement to
  find. This is precisely the `@api_view` case.
- Classes defined in a factory carry `factory.<locals>.Inner` in `__qualname__`; file and line resolve
  fine, but the qualname is not importable.

So: **source file — yes, reliably. Source line — usually, but must be optional and exception-guarded.**

### 3.5 — What breaks the walk

**`include()` with namespaces — does not break traversal, but is silently discarded.** `include()`
returns a `(urlconf_module, app_name, namespace)` tuple (`django/urls/conf.py:17-59`); `_path` turns it
into a `URLResolver` carrying `.app_name` and `.namespace`
(`django/urls/conf.py:69-79`, `django/urls/resolvers.py:503-521`). Both DRF's and drf-spectacular's
enumerators recurse on `pattern.url_patterns` and **never read `namespace` or `app_name`**
(`rest_framework/schemas/generators.py:91-96`; `drf_spectacular/generators.py:71-76`). For schema
generation that is harmless. For apiver it is not: reverse names in the wild are `ns:name`, and a
regenerated registry mounted outside that namespace changes every `reverse()` call in the host project.
apiver must track `(app_name, namespace)` per resolver level and either preserve it or report it.
(drf-spectacular does have to care in one place — `NamespaceVersioning` — and its handling is to
re-resolve the path against a rebuilt resolver, with an `error()` when that fails:
`drf_spectacular/plumbing.py:1086-1092`.)

**Nesting depth.** Unbounded plain recursion in both enumerators; no depth guard, no cycle guard. Django
does guard re-entrancy for `_populate()` via a thread-local flag
(`django/urls/resolvers.py:545-552`) but that protects reverse-lookup population, not `url_patterns`
traversal. A URLconf that includes itself yields `RecursionError`. Add a depth cap and a
visited-resolver set.

**Lazily-imported URLconfs.** Laziness is narrower than it looks. `include('dotted.path')` calls
`import_module` **immediately**, at urls.py import time (`django/urls/conf.py:38-39`). The only deferred
import is `URLResolver.urlconf_module`, a `cached_property`:

```python
# django/urls/resolvers.py:719-741
    @cached_property
    def urlconf_module(self):
        if isinstance(self.urlconf_name, str):
            return import_module(self.urlconf_name)
        else:
            return self.urlconf_name

    @cached_property
    def url_patterns(self):
        patterns = getattr(self.urlconf_module, "urlpatterns", self.urlconf_module)
        try:
            iter(patterns)
        except TypeError as e:
            msg = ("The included URLconf '{name}' does not appear to have any patterns in it. ...")
            raise ImproperlyConfigured(msg.format(name=self.urlconf_name)) from e
        return patterns
```

Consequence: **walking forces the import of every URLconf and hence every views module.** `apiver
migrate` therefore has to be a Django management command running after `django.setup()`; static source
parsing is not an option, and neither is walking in a half-initialised app registry. Accessing
`url_patterns` can also raise `ImproperlyConfigured` (circular imports) — catch it per-resolver and
report the offending `urlconf_name` rather than aborting the walk.

Note also that `django.urls.get_resolver()` returns a cached root resolver whose own pattern is `^/`
(`django/urls/resolvers.py:108-116`), so `get_resolver().url_patterns` gives the ROOT_URLCONF's
`urlpatterns` list with an extra `^/` at the root. DRF sidesteps this by importing
`settings.ROOT_URLCONF` and reading `.urlpatterns` directly
(`rest_framework/schemas/generators.py:57-70`). Either is fine; be consistent about the leading slash.

**`path()` vs `re_path()`.** `str(pattern.pattern)` returns the raw authored text in both cases:
`RoutePattern.__str__` → `str(self._route)` (`django/urls/resolvers.py:385`); `RegexPattern.__str__` →
`str(self._regex)` (`:239`). So the **route source text is recoverable losslessly**, which is what
apiver needs in order to re-emit `path(...)` / `re_path(...)`. What is *not* safe is naive
concatenation across a mixed tree: DRF builds `path_regex = prefix + str(pattern.pattern)`
(`rest_framework/schemas/generators.py:82`), which happily produces `^api/^users/$`, then relies on
`simplify_regex` (imported from `django.contrib.admindocs.views`, `:10`) plus a regex substitution to
clean it (`:100-111`). drf-spectacular has to patch one bug in that pipeline
(`drf_spectacular/generators.py:45-49`, "bugfix oversight in DRF regex stripping"). apiver should keep
each level's raw route string separately rather than flattening early — you cannot un-concatenate later.

Also note there is a hard asymmetry: a `re_path` regex generally **cannot** be re-emitted as a `path()`
route. If apiver ever wants a uniform representation it must be regex, not route syntax.

**Converters.** `RoutePattern.__init__` stores `self.converters` alongside `self._regex`
(`django/urls/resolvers.py:317-321`), a public-looking `{name: converter_instance}` dict. Custom
converters are registered globally via `register_converter`, so re-emitting the verbatim route string
(`<myconv:slug>`) keeps working without apiver knowing anything about the converter. The only place
converters bite is *path-template* generation: DRF strips them
(`_PATH_PARAMETER_COMPONENT_RE`, `rest_framework/schemas/generators.py:48-50, 110-111`) and
drf-spectacular has to rebuild whole resolvers with "de-typed" patterns using **private attributes** to
match paths without valid dummy values (`drf_spectacular/plumbing.py:1181-1221`) — `pattern._route`,
`pattern._regex`, `pattern._is_endpoint`, and `URLResolver(urlconf_name=[...])`. That is the single most
fragile piece of code in the reference implementation, and apiver does **not** need it: it never has to
re-resolve a path, only re-emit one.

DRF's `format_suffix_patterns` also registers a converter dynamically at router-build time
(`rest_framework/urlpatterns.py`, `_generate_converter_name` → `drf_format_suffix…`), which is why
spectacular special-cases `<drf_format_suffix\w*:\w+>` in operation ids
(`drf_spectacular/openapi.py:466-467`).

**`i18n_patterns`.** This is the one construct that makes the walk *non-deterministic*:

```python
# django/conf/urls/i18n.py:8-20
def i18n_patterns(*urls, prefix_default_language=True):
    if not settings.USE_I18N:
        return list(urls)
    return [URLResolver(LocalePrefixPattern(prefix_default_language=prefix_default_language), list(urls))]
```

`LocalePrefixPattern.__str__` returns `self.language_prefix`, which reads `get_language()` at call time
and returns `''` when the active language is `LANGUAGE_CODE` and `prefix_default_language=False`
(`django/urls/resolvers.py:388-419`). So the prefix apiver sees depends on the thread's active
language during the walk. Two consequences: (1) `--prefix /api/` filtering must be done with the locale
prefix normalised away, ideally by running the walk under `translation.override(settings.LANGUAGE_CODE)`
and treating `LocalePrefixPattern` as a distinct node type rather than a string; (2) a generated
registry mounted without `i18n_patterns` silently changes the URL surface. Note also that `include()`
explicitly forbids `LocalePrefixPattern` in an included URLconf
(`django/urls/conf.py:52-58`), so it can only appear at the root — a useful invariant.
drf-spectacular has no branch for `LocalePrefixPattern` in `detype_pattern`; it falls through to
`warn(f'unexpected pattern "{pattern}" encountered while simplifying urlpatterns.')`
(`drf_spectacular/plumbing.py:1220-1221`).

**Per-request URLconf swapping.** `BaseHandler.resolve_request` honours `request.urlconf` set by
middleware (`django/core/handlers/base.py:302-311`), so a project can serve an entirely different
URLconf per host/tenant. A `ROOT_URLCONF` walk cannot see those. Detectable only by grepping for
`request.urlconf` — worth a documented caveat, not a code path.

### 3.6 — How drf-spectacular does it (reference implementation)

drf-spectacular 0.30.0 does **not** write its own walk; it subclasses DRF's
(`drf_spectacular/generators.py:8, 24`):

```python
from rest_framework.schemas.generators import EndpointEnumerator as BaseEndpointEnumerator

class EndpointEnumerator(BaseEndpointEnumerator):
```

**The traversal (DRF 3.18.0, `rest_framework/schemas/generators.py:72-98`)** is fifteen lines:

```python
    def get_api_endpoints(self, patterns=None, prefix=''):
        if patterns is None:
            patterns = self.patterns
        api_endpoints = []
        for pattern in patterns:
            path_regex = prefix + str(pattern.pattern)
            if isinstance(pattern, URLPattern):
                path = self.get_path_from_regex(path_regex)
                callback = pattern.callback
                if self.should_include_endpoint(path, callback):
                    for method in self.get_allowed_methods(callback):
                        endpoint = (path, method, callback)
                        api_endpoints.append(endpoint)
            elif isinstance(pattern, URLResolver):
                nested_endpoints = self.get_api_endpoints(
                    patterns=pattern.url_patterns,
                    prefix=path_regex
                )
                api_endpoints.extend(nested_endpoints)
        return sorted(api_endpoints, key=endpoint_ordering)
```

spectacular's override (`drf_spectacular/generators.py:51-78`) is a verbatim copy with one change,
stated in its own docstring: *"Only modification the DRF version is passing through the path_regex."*
It carries the un-simplified regex alongside the cleaned path, because parameter typing needs the
original (`_resolve_path_parameters`, `drf_spectacular/openapi.py:495-500`).

**How the viewset class is recovered.** Entirely through the callback attributes:

- **class** — `rest_framework/schemas/generators.py:26-33`:
  ```python
  def is_api_view(callback):
      from rest_framework.views import APIView
      cls = getattr(callback, 'cls', None)
      return (cls is not None) and issubclass(cls, APIView)
  ```
  This is the gate: **anything without `.cls` is dropped, silently, with no warning**
  (`should_include_endpoint`, `:117-118`).
- **viewset vs APIView** — `hasattr(callback, 'actions')`
  (`rest_framework/schemas/generators.py:136`; `drf_spectacular/generators.py:81`).
- **allowed methods** — `set(callback.actions) & set(callback.cls.http_method_names)` for viewsets;
  `callback.cls().allowed_methods` (i.e. *instantiate the class*) for APIViews. spectacular extends this
  to honour an `http_method_names` override passed through `initkwargs`
  (`drf_spectacular/generators.py:80-100`) and additionally strips `TRACE`/`CONNECT`.
- **view instance** — `BaseSchemaGenerator.create_view`
  (`rest_framework/schemas/generators.py:187-208`):
  ```python
      def create_view(self, callback, method, request=None):
          view = callback.cls(**getattr(callback, 'initkwargs', {}))
          view.args = ()
          view.kwargs = {}
          view.format_kwarg = None
          view.request = None
          view.action_map = getattr(callback, 'actions', None)
          actions = getattr(callback, 'actions', None)
          if actions is not None:
              view.action = 'metadata' if method == 'OPTIONS' else actions.get(method.lower())
          ...
  ```
  This is the full recipe for reconstructing a live viewset instance from a URL pattern: class from
  `.cls`, constructor args from `.initkwargs`, current action from `.actions[method]`. spectacular
  wraps it (`drf_spectacular/generators.py:123-185`) and adds `view.swagger_fake_view = True`.

**Detail/list.** spectacular does not use `initkwargs['detail']` directly; it relies on `view.action ==
'list'` (set by `create_view` from `callback.actions`) plus the heuristic chain in
`_is_list_view` (`drf_spectacular/openapi.py:129-159`). apiver can do better for router routes by
reading the boolean out of `initkwargs`.

**Prefix.** spectacular has no notion of a router prefix. It reconstructs a *schema* path prefix by
`posixpath.commonpath()` over all discovered paths, guarded against there being only one view class
(`drf_spectacular/generators.py:210-222`), and derives tags/operation ids by tokenising the path and
taking the first non-parameter segment (`openapi.py:380-384, 451-477, 479-491`). That is a naming
heuristic, not prefix recovery — further evidence that prefix recovery has to be done from the router's
own pattern shape (§3.2), not borrowed.

**Private / undocumented APIs it relies on** (the honest list):

| API | Where | Owner |
|---|---|---|
| `callback.cls`, `callback.initkwargs`, `callback.actions` | `rest_framework/schemas/generators.py:32, 123, 136, 191`; `drf_spectacular/generators.py:81-95` | DRF, undocumented |
| `rest_framework.schemas.generators.EndpointEnumerator` / `BaseSchemaGenerator` (subclassed and partly copy-pasted) | `drf_spectacular/generators.py:7-8, 51-78` | DRF, semi-public |
| `django.contrib.admindocs.views.simplify_regex` | `rest_framework/schemas/generators.py:10` (Django 6.1 defines it at `django/contrib/admindocs/views.py:511`) | Django contrib internal |
| `URLResolver.url_patterns`, `URLPattern.callback`, `pattern.pattern` | both enumerators | Django, effectively public |
| `RoutePattern._route`, `RegexPattern._regex`, `pattern._is_endpoint`, `URLResolver(urlconf_name=[...])` | `drf_spectacular/plumbing.py:1181-1221` | **Django private** |
| `view.schema` descriptor, `_spectacular_annotation` | throughout | mixed |

**Warnings in its own source about fragility** — spectacular is candid:

- `drf_spectacular/plumbing.py:1177` — *"Cache detyped patterns due to the expensive nature of
  rebuilding URLResolver."*
- `drf_spectacular/plumbing.py:1220-1221` — `warn(f'unexpected pattern "{pattern}" encountered while
  simplifying urlpatterns.')`
- `drf_spectacular/generators.py:143-146` — *"callback.cls is hosted in urlpatterns and is therefore
  not an ephemeral modification. restore after view creation so potential revisits have a clean state
  as basis."* — i.e. it temporarily **mutates the live URLconf's callback** and must undo it. A direct
  warning that `callback.cls` is shared mutable global state.
- `drf_spectacular/generators.py:152-156` — `error('Using not supported View class. Class must be
  derived from APIView or any of its subclasses like GenericApiView, GenericViewSet.')`
- `drf_spectacular/openapi.py:131-133` — *"partially heuristic approach … defaults to False if all
  introspection fail."*
- `drf_spectacular/openapi.py:1260-1261` — *"APIView does not implement the required interface, but be
  lenient and make good guesses before giving up and emitting a warning."*
- `drf_spectacular/plumbing.py:224-230` — warns when `get_queryset()` raises, suggesting
  `queryset = Model.objects.none()` or a `swagger_fake_view` guard.
- `drf_spectacular/drainage.py:138-149` — bare `except:` around both `inspect` calls.

**The single most important finding for apiver: spectacular's enumerator is a lossy filter.** Its
`should_include_endpoint` (`rest_framework/schemas/generators.py:113-130`) drops, in order:

1. every callback without a `.cls` that subclasses `APIView` — **all plain Django views, all
   `django.views.generic` views, all undecorated function views**;
2. every view with `cls.schema is None` — including `DefaultRouter`'s own `APIRootView`
   (`rest_framework/routers.py:319`);
3. every view with `initkwargs['schema'] is None`;
4. every `.{format}` path.

Plus `get_allowed_methods` strips `OPTIONS`/`HEAD` (DRF) and additionally `TRACE`/`CONNECT`
(spectacular). The map's standing decision — *"Route composition works for anything; schema reasoning
works only for what drf-spectacular understands"* — means apiver **cannot** delegate discovery to
spectacular. It must write its own enumerator with the same traversal skeleton and no filtering,
classifying each callback into a view-type bucket and reporting the ones it cannot regenerate.

### 3.7 — Failure modes

See §5 for the full adversarial list with triggering code patterns.

---

## 4. Cannot be recovered

Explicit list. Each of these is invisible in the resolved URLconf, by construction.

1. **The router object and its class.** Only its output survives. A project using a `SimpleRouter`
   subclass with a customised `routes` table (a documented extension point,
   `docs/api-guide/routers.md:236-267`) produces patterns that a stock `DefaultRouter` will not
   reproduce. There is no marker on the pattern saying which router made it.
2. **The router-local prefix as authored** — only the absolute path is real (§3.2). The
   `include()`-prefix / router-prefix split point is unrecoverable.
3. **Which policy attributes were declared vs inherited from `api_settings`** (§3.3, note [e]).
4. **`basename` and `detail` for hand-mounted viewsets** that did not pass them
   (`rest_framework/viewsets.py:75-79` guarantees the class-level values are `None`).
5. **Detail/list for `APIView`s** — no ground truth exists; only heuristics
   (`drf_spectacular/openapi.py:129-159`).
6. **`initkwargs` values that are not repr-able back to source.** The dict is recoverable; a *source
   expression reconstructing it* generally is not (see F4).
7. **The importable name of any class or function whose `__qualname__` contains `<locals>` or
   `<lambda>`** (F1, F5).
8. **`__qualname__` of `@api_view`-generated classes** — it is always the literal `WrappedAPIView`
   (F2), and `inspect.getsourcelines` on them raises `OSError` **[probe]**.
9. **Anything behind a non-`wraps` decorator, a `functools.partial`, or a callable object** — the
   attributes are gone; DRF's `is_api_view` returns `False` and the route is dropped without a warning
   (F3).
10. **Branches of a conditionally-built URLconf that were not taken at walk time** (F12), and
    **URLconfs reachable only via `request.urlconf`** (`django/core/handlers/base.py:302-311`).
11. **Namespace/`app_name` context, if you use spectacular's or DRF's enumerator unchanged** — both
    discard it (§3.5). Recoverable, but only if apiver tracks it itself.
12. **Method-level `@action` metadata beyond what lands in `initkwargs`.** `url_path` and `url_name` are
    stored on the *function* (`rest_framework/decorators.py:227-228`), not in `initkwargs`; they are
    recoverable from `cls.get_extra_actions()` (`rest_framework/viewsets.py:175-182`), i.e. from the
    class — not from the URL pattern. Only `action.kwargs` (plus injected `name`/`description`) reaches
    `initkwargs` (`rest_framework/routers.py:212-224`, `decorators.py:235-239`).

---

## 5. Failure modes (adversarial)

Each entry: the code pattern that triggers it, what the walk sees, and why regeneration breaks.

**F1 — View class built by a factory or closure.**
```python
def make_viewset(model, serializer):
    class _VS(viewsets.ModelViewSet):
        queryset = model.objects.all()
        serializer_class = serializer
    return _VS

router.register('books', make_viewset(Book, BookSerializer), basename='book')
```
Walk sees a perfectly good `callback.cls`. `cls.__qualname__` is `make_viewset.<locals>._VS`
**[probe]** and `getattr(import_module(cls.__module__), cls.__name__, None)` is `None`. There is no
import statement that names this class. **Detection:** `'<locals>' in cls.__qualname__`, or an identity
round-trip `getattr(sys.modules[cls.__module__], cls.__qualname__.split('.')[-1], None) is cls`.
**Verdict: hard-fail with a named diagnostic.**

**F2 — `@api_view` function views (extremely common, and the qualname is a trap).**
```python
@api_view(['GET', 'POST'])
def ping(request): ...
```
`rest_framework/decorators.py:25-29` builds the class with `type('WrappedAPIView', (APIView,), …)`;
`:55-56` then sets `WrappedAPIView.__name__ = func.__name__` and `__module__ = func.__module__` —
**but not `__qualname__`** **[probe]**: `__name__` becomes `ping`, `__qualname__` stays
`WrappedAPIView`. So:
- `f"{cls.__module__}.{cls.__qualname__}"` → `myapp.views.WrappedAPIView` → **`ImportError`**.
- Django's own `URLPattern.lookup_str` (`django/urls/resolvers.py:488-500`) takes the `view_class`
  branch and produces exactly that broken string. Do not use `lookup_str` for `@api_view` routes.
- `inspect.getsourcelines(cls)` raises `OSError` **[probe]**; `getsourcefile` works.
- The re-registerable symbol is `cls.__name__` in `cls.__module__`, and the object it names is the
  **view function** (`decorators.py:88` returns `WrappedAPIView.as_view()`), not the class. So the
  identity check must be `getattr(mod, cls.__name__, None) is pattern.callback`, not `… is cls`.
  If the function was assigned to a different module-level name, or decorated inline
  (`path('p/', api_view(['GET'])(lambda r: ...))`), even that fails.

**F3 — Decorators, partials and callable objects that drop the attributes.**
```python
def audit(view):                       # no functools.wraps
    def inner(request, *a, **kw): ...
    return inner

path('reports/', audit(ReportView.as_view()))
path('legacy/',  functools.partial(SomeView.as_view(), mode='x'))
```
**[probe]:** `wraps` copies `__dict__` (so `cls`/`view_class` survive); a plain nested function does
not; `functools.partial` exposes nothing (`hasattr(p, 'cls') is False`, though `p.func` has it).
All Django-shipped view decorators are safe — `csrf_exempt`
(`django/views/decorators/csrf.py:68`), `login_required`/`user_passes_test`
(`django/contrib/auth/decorators.py:67`), `cache_page` (`django/views/decorators/cache.py:57, 83`),
`decorator_from_middleware` (`django/utils/decorators.py:197`) all end in `wraps(view_func)(…)`.
The danger is project-local decorators and third-party ones. **Consequence is silent:** DRF's
`is_api_view` returns `False` (`schemas/generators.py:32-33`) and `should_include_endpoint` drops the
route with no warning — which is exactly how these endpoints go missing from OpenAPI schemas today.
**apiver must warn loudly on any in-scope callback it cannot classify**, and should unwrap
`functools.partial` (`.func`) and `__wrapped__` chains before giving up.

**F4 — `initkwargs` that cannot be turned back into source.**
```python
path('root/', APIRootView.as_view(api_root_dict={'users': 'user-list', ...}))   # DefaultRouter's own
path('feed/', FeedView.as_view(queryset=Article.objects.filter(published=True)))
path('t/',    TemplateView.as_view(template_name='ok.html'))                    # fine — a literal
```
`DefaultRouter.get_api_root_view` (`rest_framework/routers.py:373-378`) computes `api_root_dict` from
the registry at build time. The dict is readable but meaningless to re-emit; the right regeneration is
"let the new router build its own root view", which means apiver must *recognise and special-case*
`APIRootView` rather than treat it as a generic route. Generally: `initkwargs` values survive
regeneration only if they are literals or importable module-level symbols. Everything else (querysets,
lambdas, instances, locally-built lists) needs a repr that does not exist. **Rule: emit only initkwargs
whose value round-trips through `repr()` to an equal object, or that are importable by
`__module__`/`__qualname__`; fail on the rest.**

**F5 — Lambdas and views defined inside the URLconf module.**
```python
path('healthz/', lambda r: HttpResponse('ok')),
```
`__qualname__ == '<lambda>'`. Not importable. Also common: `path('x/', SomeView.as_view())` where
`SomeView` is defined in `urls.py` itself — importable in principle
(`myproject.urls.SomeView`), but the generated registry importing from `urls.py` risks a circular
import with the very module that will include the registry.

**F6 — Programmatically generated `urlpatterns`.**
```python
urlpatterns = [
    path(f'{name}/', vs.as_view({'get': 'list'}))
    for name, vs in REGISTRY.items()          # REGISTRY from settings / entry points / DB
]
```
Every route is discoverable; the generated file freezes one snapshot of a set that was designed to
vary. Not detectable from the URLconf — detectable only by the count/shape looking suspicious. Document
as a known limitation and make `migrate` re-runnable and diffable rather than one-shot.

**F7 — Third-party nested routers (`drf-nested-routers`).**
```python
books = NestedSimpleRouter(router, r'authors', lookup='author')
books.register(r'books', BookViewSet, basename='author-books')
```
`callback.cls`, `initkwargs['basename']` and `initkwargs['detail']` are all present and correct (the
nested router still goes through `SimpleRouter.get_urls`). But the prefix contains a parent lookup group
(`^authors/(?P<author_pk>[^/.]+)/books/$`, produced via `get_lookup_regex(..., lookup_prefix=...)`,
`rest_framework/routers.py:238-248`), and re-registering it on a stock `DefaultRouter` will not
reproduce the URL. **Detection:** the derived router-local prefix contains a named capture group or a
`<…:…>` converter. Treat as "discoverable, not re-registerable via `router.register`" — emit it as an
explicit path entry instead.

**F8 — The same viewset registered more than once.** `BaseRouter.register` only guards duplicate
*basenames within one router* (`rest_framework/routers.py:56-59, 67-71`); two routers, or one viewset
mounted at several prefixes, are legal. So `cls` is **not** a route identity. This validates the map's
"path-keyed, not resource-keyed" decision: identity must be `(absolute path, method)`.

**F9 — Router callbacks have no module-level symbol at all.** `viewset.as_view(mapping, **initkwargs)`
is constructed inside the loop (`rest_framework/routers.py:307`). Nothing to import. Regeneration works
only because you re-emit the *registration*, not the callable — which is another reason apiver must
classify a route as "router-shaped" before generating, and must fail closed if the classification is
ambiguous.

**F10 — Static class introspection lies about `basename`/`detail`/`suffix`/`name`.**
`ViewSetMixin.as_view()` assigns `cls.name = cls.description = cls.suffix = cls.detail = cls.basename =
None` on the class object each call (`rest_framework/viewsets.py:66-79`). Any code that reads
`SomeViewSet.detail` gets `None`. Always read `callback.initkwargs`.

**F11 — Reading a recovered `queryset` explodes.** `APIView.as_view()` sets
`cls.queryset._fetch_all = force_evaluation`, which raises `RuntimeError`
(`rest_framework/views.py:130-137`). Anything that reprs, iterates, len()s or truthiness-tests a
recovered `queryset` — including a naive `f'{initkwargs}'` in generated output — blows up. Touch only
`queryset.model`, as `get_view_model` does (`drf_spectacular/plumbing.py:216`).

**F12 — Conditional URLconfs.**
```python
if settings.DEBUG:
    urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
if apps.is_installed('billing'):
    urlpatterns += [path('billing/', include('billing.urls'))]
```
`migrate` run under one configuration bakes in that configuration. The `--prefix /api/` filter mitigates
the debug case but not feature flags.

**F13 — `request.urlconf` per-request routing.** `django/core/handlers/base.py:302-311`. Routes served
only under an alternate URLconf are unreachable from a `ROOT_URLCONF` walk.

**F14 — `i18n_patterns` makes the prefix language-dependent.** `LocalePrefixPattern.language_prefix`
reads `get_language()` and can be `''` (`django/urls/resolvers.py:397-410`). Two walks under different
active languages produce different paths. Run the walk under an explicit
`translation.override(settings.LANGUAGE_CODE)` and model the locale prefix as a node type, not a string.

**F15 — Namespaced includes silently change `reverse()` targets.** Both reference enumerators discard
`URLResolver.namespace`/`app_name` (§3.5). If apiver regenerates `api/v1/registry.py` outside the
original namespace, every `reverse('myapp:user-list')` in the host project breaks even though every URL
still resolves. This is the failure mode most likely to pass tests and break production templates.

**F16 — `.{format}` suffix duplicates.** `DefaultRouter` runs `format_suffix_patterns` by default
(`rest_framework/routers.py:388-390`), which appends a second `URLPattern` for every route sharing the
same callback and name (`rest_framework/urlpatterns.py`, `apply_suffix_patterns`). A naive walk reports
~2× the routes. DRF drops them by path suffix (`schemas/generators.py:127-129`) and spectacular
additionally dedupes on `(path, method)` (`drf_spectacular/generators.py:31-36`). apiver must decide
deliberately: re-emit with `include_format_suffixes=True` and drop the duplicates from the registry, or
carry them.

---

## 6. Recommendations for `apiver migrate`

1. **Write apiver's own enumerator.** Copy the fifteen-line traversal shape from
   `rest_framework/schemas/generators.py:72-98`; copy none of `should_include_endpoint`. Classify each
   callback into: router-viewset · manual-viewset · APIView · `@api_view` · Django CBV · plain function
   · unknown. Filter by absolute-path prefix only, as the ticket's context specifies.
2. **Resolution order for the class:** `callback.cls` → `callback.view_class` → unwrap
   `functools.partial(.func)` / `__wrapped__` → give up and report. Never `lookup_str`, never
   `callback.__qualname__`.
3. **Read route metadata from `initkwargs`, never from the class** (F10): `basename`, `detail`,
   `suffix`, plus `actions` for the method map.
4. **Prove the import before emitting it.** For each recovered symbol, assert
   `getattr(import_module(obj.__module__), name, None) is obj` (with the `@api_view` variant comparing
   against `pattern.callback`) and reject `<locals>`/`<lambda>`.
5. **Verify by re-walking.** After generating `api/v1/registry.py`, build its patterns in-process and
   diff the set of `(absolute path, method)` against the discovered set. This is the only defence
   against F1/F4/F7/F16 and against custom routers (§4.1). A mismatch should be a hard failure with the
   offending paths listed, not a warning.
6. **Pin the DRF contract.** `.cls` / `.initkwargs` / `.actions` are undocumented. Add a test that
   asserts their presence on a router-built callback, so a DRF upgrade fails loudly in apiver's CI
   rather than silently in a user's project, and record a supported-DRF-version range.
7. **Keep raw route strings per level.** Store `(str(pattern.pattern), type(pattern.pattern))` for each
   resolver hop rather than a flattened concatenation — you cannot reconstruct the split later, and
   `re_path` regexes cannot be downgraded to `path()` routes.

---

## 7. Claims that could not be verified from source

- **Behaviour under `drf-nested-routers`** (F7) is inferred from DRF's `get_lookup_regex(…,
  lookup_prefix=…)` hook and its docstring pointing at that project
  (`rest_framework/routers.py:238-248`); the third-party source itself was not read.
- **`inspect.getsourcelines` failure mode for `@api_view` classes** was confirmed on CPython 3.13.5
  with a synthetic `type()`-built class **[probe]**, not against a real DRF-decorated view (no Django
  was executed). The `OSError` message text may differ across Python versions; the failure itself
  follows from there being no `class` statement to locate.
- **How `django-extensions show_urls` handles viewsets** is asserted only from the absence of
  `view_class` on viewset callbacks (`rest_framework/viewsets.py` never calls `View.as_view`); that
  project's source was not read.
- **Whether any DRF release note has ever promised stability for `.cls`** was not established; the only
  evidence is that DRF's own schema generator, browsable API and every third-party schema generator
  depend on it. Treat as de-facto stable, not contractual.
