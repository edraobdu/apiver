from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from healthz import healthz

# Every app owns its own urls.py and its own choice of router (DefaultRouter here,
# SimpleRouter there) — nobody sat down and picked one convention for the whole
# project, which is exactly how most real codebases end up. This root file just
# recurses into them: the thing apiver eventually has to walk is *this* resolved
# tree, however many include() layers deep it goes, not a single flat router.
urlpatterns = [
    path("api/healthz/", healthz, name="healthz"),
    path("api/", include("users.urls")),
    path("api/", include("payments.urls")),
    path("api/", include("orders.urls")),
    path("api/", include("legacy.urls")),
    path("api/", include("addresses.urls")),
    path("api/", include("notifications.urls")),
    # Deliberately the deepest mount in the project — a plausible rename target
    # for a future version (catalogue row 13), and proof the walk can't assume
    # every resource sits one segment under "api/".
    path("api/integrations/webhooks/", include("webhooks.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # apiver's Aggregation Root (ADR 0007 item 2) — adopted additively. Everything
    # above is untouched, exactly where `apiver migrate` found it.
    path("", include("api.urls")),
]
