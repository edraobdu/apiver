"""The zero-developer-effort variant: make *plain* DRF hyperlinks version-aware.

`get_url` is defined once, on `HyperlinkedRelatedField` (relations.py:321), and
`HyperlinkedIdentityField` merely subclasses it. So a single patch covers every
hyperlink shape at once — explicit fields, `HyperlinkedModelSerializer`'s
auto-generated `url`, related fields, and nested serializers — without walking a
single serializer class or asking the developer to import anything.

The patch is **version-neutral**: it rewrites the view name using whatever version is
serving *this request*, and does nothing at all when no version is serving. That is what
makes it safe to apply to a class shared by every version — unlike a register-time stamp,
it stores no version anywhere.
"""

from rest_framework.relations import HyperlinkedRelatedField

from spike.apiver_core import namespace_for

_ORIGINAL_GET_URL = HyperlinkedRelatedField.get_url


def install():
    """Idempotent. Returns True if this call actually patched."""
    if getattr(HyperlinkedRelatedField.get_url, "_apiver_patched", False):
        return False

    def get_url(self, obj, view_name, request, format):
        namespace = namespace_for(request)
        if namespace:
            view_name = f"{namespace}:{view_name}"
        return _ORIGINAL_GET_URL(self, obj, view_name, request, format)

    get_url._apiver_patched = True
    HyperlinkedRelatedField.get_url = get_url
    return True


def uninstall():
    HyperlinkedRelatedField.get_url = _ORIGINAL_GET_URL


# -- the harder half: bare reverse() -------------------------------------------

import rest_framework.reverse as _drf_reverse_module  # noqa: E402

_ORIGINAL_REVERSE = _drf_reverse_module.reverse


def _version_aware_reverse(viewname, args=None, kwargs=None, request=None, format=None, **extra):
    namespace = namespace_for(request)
    if namespace:
        viewname = f"{namespace}:{viewname}"
    return _ORIGINAL_REVERSE(
        viewname, args=args, kwargs=kwargs, request=request, format=format, **extra
    )


def install_reverse_patch():
    """Rebind `rest_framework.reverse.reverse`.

    This only reaches callers that resolve the name *after* the patch lands. A module
    that already ran `from rest_framework.reverse import reverse` holds its own reference
    and is unaffected — which makes this fix import-order dependent, tested below.
    """
    _drf_reverse_module.reverse = _version_aware_reverse


def uninstall_reverse_patch():
    _drf_reverse_module.reverse = _ORIGINAL_REVERSE
