from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def healthz(request):
    """A plain function view living outside any app — the kind of stray endpoint
    a real project accumulates. Proves function views are first-class routes too."""
    return Response({"status": "ok"})
