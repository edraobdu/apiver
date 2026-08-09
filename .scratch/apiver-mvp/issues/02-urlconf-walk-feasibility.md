# 02 — URLconf walk: what is actually recoverable?

Type: research
Status: resolved
Blocked by: —

## Question

`apiver migrate` is the adoption story: walk the project's resolved URLconf, discover the existing API, and generate `api/v1/registry.py` — importing the scattered viewsets/views from wherever they already live and registering them as the base version. **Nothing is moved; one file is generated.**

The mechanism is believed sound (drf-spectacular already walks the URLconf and recovers viewset classes and serializers for exactly this reason). This ticket establishes precisely what can and cannot be recovered, with citations to source.

Establish, for each of: **router-registered ViewSet**, **APIView subclass**, **`@api_view` function view**, **plain Django `View`**, and **`django.views.generic` views**:

1. Given a `URLPattern` from `django.urls.get_resolver().url_patterns`, what does `.callback` give you, and can you recover the originating class? (Check `ViewSetMixin.as_view()` and `APIView.as_view()` — do they attach `cls` / `initkwargs` to the returned view function, and is that public or private API?)
2. Can you recover the **prefix**, **basename**, and **detail/list distinction** for router-registered viewsets from the URLconf alone, or do you have to find the router object?
3. Can you recover `serializer_class`, `permission_classes`, `queryset`?
4. Can you recover the **source file and line** (`inspect.getsourcefile`, `__module__`, `__qualname__`)?
5. What breaks the walk: `include()` with namespaces, `URLResolver` nesting depth, lazily-imported URLconfs, `path()` vs `re_path()`, converters, i18n `i18n_patterns`?
6. How does **drf-spectacular** do this today? Read its endpoint-enumeration code and report the approach, the private APIs it relies on, and any warnings in its own source about fragility. This is the closest thing to a reference implementation.
7. What are the **failure modes** — cases where a route is discoverable but not re-registerable in a generated file (e.g. a view created by a closure or a factory function, so there's no importable symbol to name)?

Deliverable: a written report at `.scratch/apiver-mvp/research/02-urlconf-walk.md`, with a table of view-type × recoverable-attribute, every claim cited to source (Django/DRF/drf-spectacular source or docs, with version numbers), and an explicit "cannot be recovered" section.

## Context

- Settled: `migrate` **generates wiring only**, never relocates code. See map "Out of scope" for why `--move` was rejected for 0.1.
- Settled: scope filter is by URL prefix (`apiver migrate --prefix /api/`) to exclude `admin/`, `dj-rest-auth`, spectacular's own schema views — not by view type. Every view type in scope gets registered.

## Answer

Full report: [research/02-urlconf-walk.md](../research/02-urlconf-walk.md). Sources: Django 6.1, DRF 3.18.0, drf-spectacular 0.30.0 (source read at tag).

**Feasible.** Every DRF view callable in a URLconf carries a reference back to its class:
`APIView.as_view()` sets `view.cls` / `view.initkwargs` (`rest_framework/views.py:140-141`),
`ViewSetMixin.as_view()` sets `view.cls` / `view.initkwargs` / `view.actions`
(`rest_framework/viewsets.py:136-138`), and Django's `View.as_view()` sets the documented-public
`view.view_class` / `view.view_initkwargs` (`django/views/generic/base.py:107-108`). All survive
`csrf_exempt`, which uses `functools.wraps`.

**Prefix/basename/detail need no router object.** `SimpleRouter.get_urls()` injects `basename` and
`detail` into the initkwargs (`rest_framework/routers.py:301-305`), so both are read straight off the
pattern. The absolute mount path comes from concatenating `str(pattern.pattern)`; the router-local
prefix is derivable from the `{basename}-list` route. Do **not** read these off the class —
`ViewSetMixin.as_view()` resets `cls.basename`/`cls.detail`/`cls.suffix` to `None` on every call
(`viewsets.py:66-79`).

**Three findings that change the design:**

1. **drf-spectacular's `EndpointEnumerator` is not reusable.** It subclasses DRF's and copies the
   traversal verbatim, but `should_include_endpoint` drops everything without a `.cls` subclassing
   `APIView` (`rest_framework/schemas/generators.py:26-33, 117-118`) — all plain Django views,
   generic views and undecorated function views — plus `schema = None` views and `.{format}` paths,
   silently. apiver must borrow the fifteen-line traversal shape and none of the filtering.
2. **`.cls` / `.initkwargs` / `.actions` are undocumented** (zero hits across DRF 3.18.0 `docs/`;
   docstring says only "Used for breadcrumb generation"). De-facto stable — DRF's own browsable API,
   its schema generator, drf-spectacular and drf-yasg all depend on them — but pin a DRF version
   matrix and add a CI test asserting their presence.
3. **Discovery ≠ regeneration.** 16 failure modes catalogued where a route is discoverable but has no
   importable symbol: factory/closure-built classes (`<locals>` in `__qualname__`); `@api_view`, whose
   synthetic `WrappedAPIView` keeps `__qualname__ == 'WrappedAPIView'` while only `__name__` is
   rewritten, so Django's own `URLPattern.lookup_str` emits an un-importable dotted path;
   non-`wraps` decorators and `functools.partial` (silently dropped, no warning);
   unreconstructable `initkwargs` such as `DefaultRouter`'s `APIRootView(api_root_dict=...)`;
   nested routers; `i18n_patterns`, whose prefix depends on the active language at walk time;
   namespaced includes, which both reference enumerators discard, so `reverse()` targets can break
   while every URL still resolves.

**Consequences for `migrate`:** it must be a management command (walking forces import of every
URLconf and views module — `URLResolver.url_patterns` is a `cached_property` that imports); resolution
order is `callback.cls` → `callback.view_class` → unwrap `partial`/`__wrapped__` → report, never
`lookup_str`; every emitted import must be identity-checked against the live object; and generation
must be **verified by re-walking the generated registry and diffing `(absolute path, method)` against
the discovered set**, hard-failing on mismatch. Route identity is `(path, method)`, not the class — the
same viewset can legally be registered at several prefixes, confirming the path-keyed decision.
