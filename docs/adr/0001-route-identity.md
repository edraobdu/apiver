---
status: accepted
---

# Routes are identified by absolute path, and a whole registration is the smallest unit of override

apiver composes a complete API version from a parent version plus a set of deltas, so it needs a stable
key to decide "does V2 override this route, or does it fall through to V1?". The obvious key — the
resource name, as in `resolve(v2, "payments")` — assumes every route is a router-registered ViewSet, and
most real DRF projects also serve `APIView`s, `@api_view` functions, and plain Django views. We therefore
key the resolution table on the **absolute path pattern**, carry DRF's own route metadata alongside it as
a `RouteIdentity`, and make a **whole registration** the smallest thing a version may override or remove.

## Considered options

**Resource name as the key** (`payments`). Rejected: only router-registered ViewSets have one. An
unnamed `path('healthz/', view)` is still part of the API surface and must compose like anything else.

**Logical identity as the key** (`payments.detail`, from `(basename, action)`). Rejected as the *key*,
kept as *metadata*. It doesn't exist for non-ViewSet routes, and the class cannot supply it: the same
ViewSet may legally be registered at several prefixes, and `ViewSetMixin.as_view()` resets
`cls.basename`, `cls.detail` and `cls.suffix` to `None` on every call
([`viewsets.py:66-79`](https://github.com/encode/django-rest-framework/blob/3.18.0/rest_framework/viewsets.py#L66-L79)),
so introspecting the class does not merely fail — it returns stale values from an unrelated registration.

**Per-route override** (V2 overrides `payments.detail` only, leaving list and actions on V1). Rejected;
see Consequences.

## Decision

1. **The key is the absolute path pattern.** It is the only identifier every route type possesses, and it
   is what clients actually call — which is the contract versioning exists to protect. drf-spectacular
   independently derives operationIds from the path rather than the view
   ([`plumbing.py:1239-1253`](https://github.com/tfranzel/drf-spectacular/blob/0.30.0/drf_spectacular/plumbing.py#L1239-L1253)),
   so the schema layer already agrees with this choice.

2. **Every entry carries a `RouteIdentity`** — `basename`, `action`, `detail`, `url_name`, `methods` — as
   first-class metadata. This is read from the URLconf, not inferred: `SimpleRouter.get_urls()` bakes
   `basename` and `detail` into the view's `initkwargs`
   ([`routers.py:301-305`](https://github.com/encode/django-rest-framework/blob/3.18.0/rest_framework/routers.py#L301-L305)),
   and `callback.actions` holds the method→action map. `detail` is a real boolean, not a heuristic.
   Diffing needs this: keyed on path alone, moving `/payments/` to `/transactions/` reads as one deletion
   plus one addition; with identity carried alongside it reads as a **rename**, which is the more useful
   thing to report.

3. **A whole registration is the unit of override and of removal.** Overriding `payments` replaces every
   path entry that registration expanded into. Sub-route override is refused loudly at registration time.

4. **The base version keeps bare URL names; authored versions are mounted under Django instance
   namespaces.** `reverse('payments-detail')` continues to resolve to the base version;
   `reverse('v2:payments-detail')` reaches V2.

5. **Nested routers and non-`SimpleRouter`/`DefaultRouter` routers are refused in 0.1**, detected and
   hard-failed at registration. Composition additionally **verifies itself**: after building a version,
   apiver re-walks the result and diffs the set of `(absolute path, method)` against what it intended to
   produce, failing hard on any mismatch.

## Consequences

**Sub-route override is impossible, deliberately.** Letting V2 override only `payments.detail` would put
two different classes behind one resource, so `get_queryset()`, `permission_classes` and filter backends
would diverge invisibly between list and detail — destroying the claim that a version delta is ordinary,
inspectable Python inheritance, and leaving squash with no single class to flatten. A developer who
genuinely needs per-route divergence can split the resource into two registrations in the base version.
Prior-art research found that nobody has shipped inheritance-based whole-API-surface composition in any
framework, and flagged sub-resource-granularity override as a candidate reason; we think the answer is
that it should not be supported.

**URL naming is asymmetric, and that asymmetry is load-bearing.** Router patterns are named
`{basename}-{url_name}`, so mounting V1 and V2 without namespacing gives two patterns called
`payments-detail`, with `reverse()` silently resolving to whichever registered last. Every URL still
resolves and every routing test still passes, while `HyperlinkedIdentityField`, redirect targets and
`Location` headers quietly point at the wrong version. Namespacing every version would break every
existing `reverse()` call in an adopting project, contradicting the promise that adoption changes no
existing code — so the base version keeps its bare names and only authored versions are namespaced. What
a V2 `HyperlinkedIdentityField` should resolve to within its own version is not settled here.

**Aliases are not covered by this decision.** Mounting one router at both `/api/v2/` and `/api/stable/`
causes drf-spectacular to duplicate every operation *silently* — its deduplication keys on
`(path, method)`, not on the callback — so the "just mount it twice" approach proposed in early design
conversations is unsafe. Aliases need their own handling.

**apiver depends on undocumented DRF attributes.** `callback.cls`, `callback.initkwargs` and
`callback.actions` appear nowhere in DRF's documentation, though DRF's own browsable API and schema
generator, drf-spectacular and drf-yasg all rely on them. Treat as de-facto stable, not contractual: pin
a supported DRF version range and assert their presence in CI so an upgrade fails loudly in apiver rather
than silently in a user's project.
