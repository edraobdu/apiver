"""Patches `HyperlinkedRelatedField.get_url` so every hyperlink an inherited
serializer produces resolves within the Version actually serving the
request (ADR 0005 items 5-8).

Applied to the class itself, once, from `ApiverConfig.ready()` — the
developer never imports or configures anything. `get_url` is defined once on
`HyperlinkedRelatedField`; `HyperlinkedIdentityField` merely subclasses it,
so this one patched method covers explicit fields,
`HyperlinkedModelSerializer`'s auto-generated `url`, related/FK fields and
nested serializers at once. It is late-bound (`self.get_url(...)` resolves
through the class at call time), so a field instance built long before the
patch is applied still routes into it, and a developer who overrides
`get_url()` on their own subclass is simply not covered — they have taken
control of link generation explicitly (item 8).
"""

from typing import Any

from django.conf import settings
from rest_framework.relations import HyperlinkedRelatedField

from .reverse import reverse

_original_get_url = HyperlinkedRelatedField.get_url


def _versioned_get_url(self: HyperlinkedRelatedField, obj: Any, view_name: str, request: Any, format: Any):
    """Same body as DRF's own `get_url`, except it calls `apiver.drf.reverse`
    instead of `self.reverse` (`rest_framework.reverse.reverse`, bound in
    `__init__`). Checked live, on every call, against
    `APIVER_PATCH_HYPERLINKED_FIELDS` rather than only once when the patch
    is applied — the documented escape hatch (ADR 0005 Consequences), and
    what makes it independently testable with `override_settings` in a
    process where `AppConfig.ready()` has already run.
    """
    if getattr(settings, "APIVER_PATCH_HYPERLINKED_FIELDS", True) is False:
        return _original_get_url(self, obj, view_name, request, format)

    if hasattr(obj, "pk") and obj.pk in (None, ""):
        return None
    lookup_value = getattr(obj, self.lookup_field)
    kwargs = {self.lookup_url_kwarg: lookup_value}
    return reverse(view_name, kwargs=kwargs, request=request, format=format)


def patch_hyperlinked_related_field() -> None:
    """Idempotent: safe to call more than once — checked by asking the class
    itself whether it's already patched, rather than tracking a second,
    separately-mutable flag that could drift out of sync with it — and a
    no-op on projects that never installed apiver, since nothing calls this
    without `"apiver"` in `INSTALLED_APPS`. The patched method itself stays
    inert (falls through to the exact behaviour it replaced) whenever no
    Version is serving (ADR 0005 item 6)."""
    if HyperlinkedRelatedField.get_url is _versioned_get_url:
        return
    HyperlinkedRelatedField.get_url = _versioned_get_url
