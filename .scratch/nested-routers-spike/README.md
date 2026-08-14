# Spike: nested routers — authoring and adoption

Throwaway branch `spike/nested-routers`, off `master`. Not for merging as-is; the one real fix
(`src/apiver/drf/init.py`'s `_strip_anchors`) is being lifted into its own clean PR. Everything else
here — the `reference/` app changes, the generated-and-discarded `apiversions/` output — is scratch
evidence for the "support nested routers" decision ticket.

## Hypothesis going in

DRF's `SimpleRouter.get_urls()` splices `prefix` verbatim into its route templates with no validation
(`rest_framework/routers.py`, `SimpleRouter.routes`). So a prefix that embeds the parent's lookup regex
(`r"orders/(?P<order_pk>[^/.]+)/items"`) should already produce correct nested paths through plain
`register()` — no new apiver mechanism. And `init.py`'s adoption-walk refusal only inspects
`ancestor_prefix` (the `include()`/`URLResolver` chain *above* a router's own mount), never the
router-local prefix `_derive_router_prefix()` recovers — and both the hand-rolled trick and
`drf-nested-routers`' `NestedSimpleRouter` bake the parent lookup into that router-local prefix, not
into a separate parameterized `include()`. Predicted: both authoring and adoption already work.

## What was built

- `reference/orders/`: `OrderItem` model + `OrderItemViewSet`, registered by hand in `orders/urls.py`
  with `router.register(r"orders/(?P<order_pk>[^/.]+)/items", OrderItemViewSet, basename="order-items")`
  — no router library. Tests the manual-prefix variant.
- `reference/catalog/` (new app): `Category`/`Product`, `ProductViewSet` nested under `Category` via
  `drf-nested-routers`' `NestedSimpleRouter` (added as a reference-project dependency). Tests the
  third-party-library variant.
- Ran `apiver init --base v1 --prefix api/` against the whole reference project (all six pre-existing
  apps plus these two) from a clean checkout each time.

## Findings

1. **Authoring already works, confirmed, no apiver changes needed.** `v1.register(r"orders/(?P<order_pk>[^/.]+)/items", OrderItemViewSet, basename="order-items")`
   composes, resolves, and reverses correctly through plain `register()`. Verified directly (no `init`
   involved): `resolve()`/`reverse()` round-trip, `override()` replacing the nested registration cleanly,
   `remove()` dropping only the child and leaving the parent `orders` resource untouched, and
   drf-spectacular schema generation producing the nested path with `order_pk`/`category_pk` as real
   path parameters (`/api/v1/orders/{order_pk}/items/`, etc. — see full parameter list in session log).
   `_classify`'s router-object refusal is orthogonal to this and correctly untouched: it exists to reject
   passing an actual router *instance* as a handler, which was never how nesting needs to be expressed.

2. **Adoption walk does NOT refuse either variant** — half the hypothesis confirmed outright. The
   `ancestor_relative`/`"(?P<" in ancestor_relative` check in `discover()` never fires for either
   `orders/`'s hand-rolled prefix or `catalog/`'s `NestedSimpleRouter`, because in both cases the
   parent-lookup group lives in the router's own local prefix, not in an ancestor `include()`.

3. **But adoption silently produced a broken route — a real, independent bug, not a nested-router
   gap.** `init.py`'s `_strip_anchors()` did `text.replace("^", "").replace("$", "")` on the
   concatenated `ancestor_prefix + declared` string. DRF's default `lookup_value_regex` is the negated
   character class `[^/.]+`; the blind replace stripped that `^` too, turning `[^/.]+` into `[/.]+` —
   "only slash or dot" instead of "not slash or dot". The generated `registry.py` looked plausible
   (`v1.register('orders/(?P<order_pk>[/.]+)/items', ...)`) and `apiver init` exited having written both
   files with no error. Composed and mounted for real, `/api/v1/orders/42/items/` came back
   `Resolver404` — a silent, complete breakage of exactly the kind apiver's own philosophy (see
   `docs/supported.md`) is built to refuse, except here the silent failure was in apiver's own tooling,
   not a user's code. Nothing in `_verify()`'s self-check catches it, because the "intended" key it
   diffs against was already corrupted upstream, before composition ever ran.

   This was never caught before because nested prefixes were always refused prior to reaching this
   code path — the bug was latent, waiting for nesting to be allowed through at all.

4. **Fix applied and verified**: strip anchors from the leaf's own `declared` text before concatenating
   with `ancestor_prefix` (not after), and use `removeprefix("^")`/`removesuffix("$")` instead of a
   global replace — SimpleRouter's route templates (`^{prefix}...{trailing_slash}$`) only ever anchor at
   position 0/-1 of the leaf's own text, never elsewhere, so this can't strip a `^`/`$` that's part of
   the pattern's actual content. Full apiver test suite (362 tests) still green. Re-ran `init` against
   the reference project: both nested resources now adopt with the correct regex, resolve, reverse, and
   schema correctly (`/api/v1/orders/{order_pk}/items/`, `/api/v1/categories/{category_pk}/products/`).
   `override()`/`remove()` on the adopted nested registration re-verified too — ordinary Registration
   semantics, no special-casing needed.

5. **Not tested / left open**: nesting expressed via a parameterized `include()` itself
   (`path("orders/<int:pk>/", include(child_router.urls))`, parent lookup in the *ancestor* segment
   rather than the router's own prefix) — genuinely still hits `discover()`'s refusal, untouched by this
   fix. Narrower and rarer than the two variants tested here; not attempted in this spike.

## What this resolves vs. leaves open

- The `_strip_anchors` fix is a real, narrowly-scoped, independently-mergeable bug fix — lifted to its
  own branch/PR, not bundled with this spike.
- Whether apiver should also gain a friendlier, dedicated authoring primitive (vs. "hand-write the regex
  correctly, which is exactly what this spike found people/tools get wrong") is the open ergonomics
  question — filed as a separate spike ticket, not resolved here.
- The `include()`-nested adoption case is left open, filed as a known gap rather than investigated
  further, per scope.
