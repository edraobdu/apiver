# 12 — Gating semantics in detail

Type: grilling
Status: resolved
Assignee: claude
Blocked by: 07, 08

## Question

The exact runtime behavior of version lifecycle enforcement — everything that happens *because* a Version
is Deprecated or Sunset, or because a request names a Version that doesn't exist.

1. **Deprecation signaling.** Exact `Deprecation` / `Sunset` HTTP header formats (RFC 8594 / the draft
   `Deprecation` header convention?) for a request served by a Deprecated Version. Emitted by middleware,
   a mixin, or something the composing router attaches automatically to every response?
2. **Sunset enforcement.** What happens to a request against a Version past its sunset date — a hard 410
   Gone, per the `Sunset` glossary entry? Does apiver enforce this automatically once the date passes, or
   does hitting sunset require a deploy (freezing the check at process-start config vs. checking wall-clock
   time on every request)? Note per [09](09-squash-feasibility.md)/[ADR 0004](../../../docs/adr/0004-squash-feasibility.md): a Sunset Version stays `Live` (still mounted, still needs code to answer 410) — it only becomes `Archived` when its mount is removed, which is a separate, later decision from sunset itself.
3. **Unknown-version gating.** A request for a Version that was never registered, or an Alias pointing
   nowhere. 404, or a distinguishable error shape?
4. **Where does this read from?** Per [08](08-layout-and-manifest.md) item 8, gating reads live `Version`
   objects, never `apiver.toml` — confirm the specific attributes read (`deprecated`, `sunset_date`) and
   that no new manifest fields are needed beyond what [08](08-layout-and-manifest.md) item 6 already
   specified.

## Context

- Settled: deprecation lives on the `Version` object, never the manifest — [ADR 0002](../../../docs/adr/0002-public-api-surface.md) item 5.
- Settled: aliases are declared independently and mounted via reused callbacks under their own namespace — [ADR 0002](../../../docs/adr/0002-public-api-surface.md) item 8.
- Settled: the manifest is a generated snapshot the running server never reads — [ADR 0003](../../../docs/adr/0003-layout-and-manifest.md) item 8.
- Graduated from the map's "Gating semantics in detail" fog patch once both blockers above landed.

## Answer

1. **Emission mechanism: a mount-time wrapper, not global middleware.** Deprecation/Sunset headers and sunset enforcement are attached by wrapping a Version's URL patterns at mount time — extending how `v2.urls` already returns `(patterns, app_name)` per [ADR 0002](../../../docs/adr/0002-public-api-surface.md) item 7 — closing directly over the `Version` object rather than reverse-engineering "which Version served this request" from `request.resolver_match`. The latter breaks specifically for the Base Version, which ADR 0001 leaves unnamespaced. A mount-time wrapper works uniformly across ViewSets, APIViews, function views, and plain Django views, since it sits at the routing layer, not the view layer — consistent with the standing "first-class routes" decision.

2. **Header formats.** `Sunset: <HTTP-date>` per RFC 8594, used as-is. `Deprecation: true` (the boolean form of the draft header) — no explicit deprecation-start timestamp. `v1.deprecate(sunset=...)` does not grow a start-date parameter; nothing consumes "when did this become deprecated," only the sunset date matters operationally.

3. **Sunset timing: wall-clock, evaluated per request.** `timezone.now() >= version.sunset_date`, checked fresh on every request against the live object already in memory — not frozen at process start. This is what makes a sunset date declared in advance actually take effect on schedule, without requiring a deploy timed to land exactly on that date.

4. **410 response: short-circuits before the view runs.** Once past sunset, the mount-time wrapper returns `410 Gone` with body `{"detail": "This API version has been sunset."}` — DRF's ordinary exception-response shape — without invoking the wrapped view or serializer at all.

5. **Unknown-version gating: plain Django 404, nothing apiver-specific to build.** Path-keyed resolution plus explicit per-Version mounting (`path("api/v2/", include(v2.urls))`) means an unmounted Version's prefix simply has no entry in `urlpatterns` — Django 404s on its own. An `Alias(target=...)` pointing at a broken reference fails loudly at declaration time (module import), not at request time, so there is no request-time "alias points nowhere" case to gate either. A friendlier distinguishable error shape is a plausible future nicety, explicitly not built in 0.1.

6. **Read source confirmed.** Gating reads exactly `Version.deprecated` (bool) and `Version.sunset_date` (datetime) off the live object — the same two attributes [ADR 0003](../../../docs/adr/0003-layout-and-manifest.md) item 6 already specified for the manifest snapshot. No new manifest fields needed.

**Correction made while resolving this ticket:** `CONTEXT.md`'s `Manifest` glossary entry still listed "version gating" as a manifest reader, left over from before ADR 0003 item 8 reclassified gating onto live `Version` objects. Corrected as part of closing this ticket, not a new decision.
