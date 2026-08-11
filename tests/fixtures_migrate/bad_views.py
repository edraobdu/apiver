"""Adversarial handlers proving `apiver migrate` fails loudly instead of
silently mis-emitting a broken registry.py (ticket 02's catalogued failure
modes, ticket 17)."""

from rest_framework import viewsets
from rest_framework.response import Response


def make_gizmo_viewset():
    """F1: a factory/closure-built class — `cls.__qualname__` contains
    '<locals>' and there is no import statement that names it."""

    class _GizmoViewSet(viewsets.ViewSet):
        def list(self, request):
            return Response({"results": []})

    return _GizmoViewSet


GizmoViewSet = make_gizmo_viewset()
