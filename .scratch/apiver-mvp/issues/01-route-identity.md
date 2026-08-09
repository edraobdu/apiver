# 01 — Route identity: what is the unit of override?

Type: grilling
Status: resolved
Blocked by: —

## Question

ChatGPT's proposed model is **resource-keyed**: `resolve(v2, "payments") → v1.payments`. That quietly assumes every route is a router-registered viewset. It isn't.

- A **viewset** is keyed by *prefix* (`payments`), and DRF's router expands it into list, detail, and `@action` routes.
- An **APIView** is keyed by a *concrete path* (`payments/summary/`). No prefix, no basename, no expansion.
- A **function view** (`@api_view`) and a plain Django `View` are the same shape as an APIView.

The charting session settled the direction: **the resolution table is path-keyed**, and a registered viewset is something that *expands into* several path entries. This ticket pins down what that actually looks like.

Decide:

1. **What is the key?** The resolved path pattern? A normalised route identity (`payments.list`, `payments.detail`)? Both — a logical identity plus the path it renders to? Note ChatGPT §9 distinguished *logical identity* (`payments.list`) from *documentation identity* (`payments_list_v1`); is that distinction load-bearing here, or is it only an OpenAPI concern?

2. **What is the unit of override?** If V2 overrides `payments`, does it replace *all* path entries the V1 viewset expanded into, or can it replace a single one (e.g. only `payments.detail`)? Sub-resource-granularity overrides are where the research flagged a possible structural problem in inheritance-based composition — decide whether they're supported or explicitly refused.

3. **How do `@action` routes compose?** A V2 viewset inheriting V1 inherits its `@action` methods, so the router will expand them. But what if V2 wants to *remove* an inherited action, or add one? Does that fall out of Python inheritance for free, or does it need library support?

4. **How does `remove()` key work?** Route-level removal is non-negotiable (without it, "V2 is a complete API" is a lie). Does `v2.remove("payments")` drop the whole prefix, and is there a way to drop one route of a viewset?

5. **Nested routers** (`drf-nested-routers` or hand-rolled). Do they compose, or are they explicitly unsupported in 0.1?

6. **Same handler mounted twice** under different prefixes or namespaces — does the model tolerate it?

The output is the core data structure of the library. Almost everything else is blocked on it.

## Context

- [research/01-prior-art.md](../research/01-prior-art.md) — §"risks to the apiver thesis" notes that nobody has built inheritance-based whole-API-surface composition in any framework, and flags partial overrides at sub-resource granularity as a candidate reason why.

## Answer

Recorded as [ADR 0001 — Routes are identified by absolute path, and a whole registration is the smallest unit of override](../../../docs/adr/0001-route-identity.md), with the glossary in [CONTEXT.md](../../../CONTEXT.md). GitHub issue [#1](https://github.com/edraobdu/apiver/issues/1); PR [#2](https://github.com/edraobdu/apiver/pull/2).

1. **Key = absolute path pattern.** The only identifier every route type has, and what clients actually call. The class cannot be the identity: the same ViewSet may be registered at several prefixes, and `ViewSetMixin.as_view()` resets `cls.basename`/`detail`/`suffix` to `None` on every call (`viewsets.py:66-79`), so class introspection returns stale values. drf-spectacular independently keys operationIds on path, so the schema layer agrees.
2. **Each entry carries a `RouteIdentity`** — `basename`, `action`, `detail`, `url_name`, `methods` — read from `initkwargs` (`routers.py:301-305`), not inferred. `detail` is a real boolean. Needed so `diff` can report a moved path as a *rename* rather than a delete plus an add.
3. **Whole registration is the unit of override and removal.** Sub-route override refused loudly. It would put two classes behind one resource (divergent `get_queryset()`, permissions, filters between list and detail), break the "just Python inheritance" pitch, and leave squash no single class to flatten. Escape hatch: split the resource into two registrations in the base version.
4. **Base version keeps bare URL names; authored versions get Django instance namespaces** (`reverse('v2:payments-detail')`). Without this, two patterns share `payments-detail` and `reverse()` silently resolves to the last registered — URLs still resolve, tests still pass, `HyperlinkedIdentityField` and `Location` headers point at the wrong version. Namespacing every version would break existing `reverse()` calls, contradicting the adoption promise, hence the asymmetry.
5. **Nested and custom routers refused in 0.1**, hard-failed at registration. Composition **verifies itself**: re-walk the built version and diff `(absolute path, method)` against intent, hard-failing on mismatch.

**Deferred out of this ticket:** inherited `@action` removal → [06](06-field-removal.md). Alias handling → fog. What a V2 `HyperlinkedIdentityField` resolves to within its own version → fog.
