"""`apiver.drf.reverse` — the version-aware drop-in for `django.urls.reverse`
and `rest_framework.reverse.reverse` (ADR 0005 items 9-10).

apiver patches neither of those two — DRF's is bound at import
(`from django.urls import reverse as django_reverse`), and fifteen-plus
modules inside Django itself already hold a direct reference to Django's own,
so nothing short of an ordering guarantee could make patching either
reliable, and a silent order-dependent wrong URL is a worse trade than asking
an adopting project to change an import. `apiver.drf.reverse` is a
mechanical find-and-replace instead.
"""

from django.conf import settings
from django.urls import NoReverseMatch
from rest_framework.reverse import reverse as _drf_reverse

from .version import current_version


def _namespace_for(request) -> str | None:
    """Which URL namespace should a link generated right now use?

    Three sources, in this order (ADR 0005 item 4):

    1. `request.resolver_match.namespace` — the *instance* namespace Django
       actually matched. This is what makes a request that arrived through
       an Alias keep producing Alias-rooted links (item 14) rather than
       leaking the concrete Version it resolves to.
    2. the Version stamped onto the request by `Version._wrap` at mount
       time — covers the unnamespaced Base Version, which
       `resolver_match.namespace` cannot identify at all.
    3. the `current_version` ContextVar — the same stamp, for code with no
       request in reach (a bare `reverse()`, a model's
       `get_absolute_url()`).

    With none of those, this is genuinely out-of-band code — a Celery task,
    a management command, a cron job — and falls back to
    `APIVER_OUT_OF_BAND_ALIAS` (item 11). Left unset, the result is `None`,
    reproducing the pre-ADR-0005 behaviour of resolving against the bare,
    unnamespaced names.
    """
    if request is not None:
        match = getattr(request, "resolver_match", None)
        if match is not None and match.namespace:
            return match.namespace
        version = getattr(request, "apiver_version", None)
        if version is not None:
            return version.namespace

    version = current_version.get()
    if version is not None:
        return version.namespace

    return getattr(settings, "APIVER_OUT_OF_BAND_ALIAS", None)


def reverse(viewname, *, request=None, args=None, kwargs=None, format=None, **extra):
    """A genuine drop-in for both Django's `reverse()` and DRF's: a relative
    path with no request, an absolute URI when given one, and every
    Django-only keyword (`query`, `fragment`, ...) passed through.

    Tries the namespaced name for the Version serving this call first, and
    falls back to the bare name when that doesn't resolve (ADR 0005 item
    10) — load-bearing, since a project that replaced every `reverse()` call
    with this one still needs its admin, login page and health check to
    resolve while a versioned request is being served. It does not downgrade
    a versioned route to the Base Version: `NoReverseMatch` on a genuinely
    unknown name still raises.
    """
    namespace = _namespace_for(request)
    if namespace:
        try:
            return _drf_reverse(
                f"{namespace}:{viewname}",
                args=args,
                kwargs=kwargs,
                request=request,
                format=format,
                **extra,
            )
        except NoReverseMatch:
            pass  # not a route of this Version — fall through to the bare name
    return _drf_reverse(viewname, args=args, kwargs=kwargs, request=request, format=format, **extra)
