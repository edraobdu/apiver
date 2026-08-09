# 12 — Gating semantics in detail

Type: grilling
Status: open
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
