from django.urls import include, path

# apiver's Aggregation Root (api/urls.py) composes every Live version's mount at
# its own full absolute path. This root urls.py includes it once, at "", and is
# never touched again for a version's sake (ADR 0007 item 2) — the per-app
# include()s that used to live here moved into api/v1/registry.py when
# `apiver migrate` adopted this project as the base version.
urlpatterns = [
    path("", include("api.urls")),
]
