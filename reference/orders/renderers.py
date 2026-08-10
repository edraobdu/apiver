from rest_framework.renderers import BaseRenderer


class OrdersCSVRenderer(BaseRenderer):
    """Minimal, hand-rolled — no `django-import-export`/`drf-renderer-csv` dependency
    for one endpoint. A future version swapping the renderer, or changing which
    columns it emits, is catalogue row 21 (content negotiation/renderer changes):
    writable in an afternoon, invisible to a schema diff."""

    media_type = "text/csv"
    format = "csv"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        rows = ["id,reference,status"]
        for order in data:
            rows.append(f"{order['id']},{order['reference']},{order['status']}")
        return "\n".join(rows).encode("utf-8")
