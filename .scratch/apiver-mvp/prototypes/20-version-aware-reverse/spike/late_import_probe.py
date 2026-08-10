"""Stands in for a developer module that does the ordinary DRF import.

Whether this module sees apiver's patched reverse depends entirely on whether it was
imported before or after the patch landed — which is the whole point of the probe.
"""

from rest_framework.reverse import reverse


def build_link(pk, request=None):
    return reverse("payment-detail", kwargs={"pk": pk}, request=request)
