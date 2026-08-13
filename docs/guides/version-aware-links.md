# Version-Aware Links: `apiver.drf.reverse`

Every version gets its own Django instance namespace, so an ordinary `reverse("products-detail")`
called from inside a V2 view can't be trusted to resolve back into V2's own URLs — nothing about a bare
`reverse()` call knows which version is serving the request. `apiver.drf.reverse` is a drop-in
replacement for both `django.urls.reverse` and DRF's `rest_framework.reverse.reverse` that resolves
against the version actually serving the current request first:

```python
from apiver.drf import reverse

reverse("products-detail", request=request, kwargs={"pk": product.pk})
```

It isn't a monkeypatch — DRF's own `reverse` is bound at import time in fifteen-plus places inside
Django itself, so nothing short of an ordering guarantee could make patching it reliable.
`apiver.drf.reverse` is a mechanical find-and-replace instead: swap the import, keep every other
argument (`args`, `kwargs`, `format`, and Django-only keywords like `query`/`fragment`) exactly as it
was.

## Resolution order

Namespace resolution checks, in order:

1. The namespace Django actually matched on the request — so a request that arrived through an `Alias`
   keeps producing `Alias`-rooted links, not the concrete version underneath it.
2. The `Version` stamped onto the request at mount time.
3. For code with no request in reach at all (a Celery task, a management command), the
   `current_version` contextvar.
4. If none of those apply and `APIVER_OUT_OF_BAND_ALIAS` is set, that's the final fallback.

A name that doesn't resolve under the chosen namespace falls back to the bare name — load-bearing,
since a project that replaced every `reverse()` call with this one still needs its admin, login page,
and health check to resolve while a versioned request is being served — but a genuinely unknown name
still raises `NoReverseMatch`.

## Out-of-band code needs one of two different answers, not one

For most Celery tasks, cron jobs, and management commands — the ordinary case, where a link just needs
to point at "whatever's current" — point `APIVER_OUT_OF_BAND_ALIAS` at your rolling `Alias` (`stable`,
`latest`). The task keeps generating correct links as that `Alias` is re-pointed at newer versions over
time, with no code change on its side.

But a link that has to stay valid on its own timeline can't ride an `Alias` that may have moved on by
the time anything follows it — and that shows up mostly in API-to-API integration patterns, not
user-facing ones, since the links in question are raw API endpoint URLs rather than frontend pages:

- **A webhook payload's callback URL** — the receiving system stores it and may call back into it
  hours or days after the original event.
- **A paginated response's `next`/cursor link**, when the consumer is a batch sync job rather than a
  browser session — it persists the cursor and resumes from it later, sometimes the next day's run.
- **A HATEOAS-style `refund_url`/`cancel_url` embedded in an order or subscription resource**, which
  the calling system (a merchant's backend, a billing integration) stores alongside its own record and
  calls back into weeks or months after the original request, well past any single deploy's lifetime.

For those, resolve against a specific `Version`'s namespace directly
(`reverse(f"{v2.namespace}:products-detail", ...)`) instead of letting `apiver.drf.reverse` pick one for
you: a `Version`'s namespace is fixed for as long as the `Version` exists, `Alias` or no `Alias`, so the
link keeps meaning exactly what it meant the day it was generated.

`HyperlinkedRelatedField` and friends get the same version-aware resolution automatically, via a small
patch DRF's `get_url` applies on import; set `APIVER_PATCH_HYPERLINKED_FIELDS = False` to opt out. See
[ADR 0005](https://github.com/edraobdu/apiver/blob/master/docs/adr/0005-intra-version-hyperlinking.md)
for the full design.
