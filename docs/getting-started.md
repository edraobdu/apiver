# Adopting apiver into an existing project

Nothing below assumes a clean starting point. Whatever your project's API looks like today — one
version or a dozen, a consistent scheme or several abandoned ones, hand-rolled `if request.version`
branches you'd rather not think about — apiver adopts your project's current, live routes as the **Base
Version**, exactly where they already are. From that point on, your *next* version is the first one
apiver actually manages; everything before it stays exactly as it was.

This walks that adoption start to finish, against a small commerce API — `users`, `orders`, `payments`,
`webhooks`, `addresses`, `notifications`, `legacy-invoices` — through installing apiver, wrapping the
existing API as `v1`, then shipping a `v2` that changes exactly one thing. Every command and every line
of output below is copied verbatim from an actual run, not written up from memory.

## Prerequisites

- `django~=5.2`, `djangorestframework~=3.18`, `drf-spectacular~=0.30` — apiver's own dependency range,
  so adding it resolves cleanly against a project already on these.
- An API reachable by walking `ROOT_URLCONF`: plain `path()` entries, router-registered ViewSets with
  an explicit `basename=`. `apiver init` refuses, writing nothing, on anything it can't classify — see
  the [Reference](reference.md#cli) for the full list.

## Get v1 live

### 1. Install it

```console
$ uv add apiver
Resolved 18 packages in 7ms
Installed 2 packages in 3ms
 + apiver==0.0.1
 + tomli-w==1.2.0
```

(or `pip install apiver`, if you're not on `uv`.) On a project already pinned to the versions above,
that's the entire dependency footprint — apiver doesn't drag in a second HTTP client, a second test
runner, anything.

Add it to `INSTALLED_APPS` — it has no models, but its checks won't run until it's listed:

```diff
 INSTALLED_APPS = [
     "django.contrib.contenttypes",
     "django.contrib.auth",
     "rest_framework",
     "drf_spectacular",
+    "apiver",
     "users",
     "payments",
     ...
 ]
```

### 2. Add two settings

```python
# settings.py, anywhere after INSTALLED_APPS
APIVER_ROOT_PREFIX = "api/"  # where every version mounts, in the URL
APIVER_VERSIONS = ["v1"]  # which versions are live
```

apiver's own generated code lives under `apiversions/` by default — deliberately not `api`, so it can
never collide with a project that already has its own `api` package. Only add
`APIVER_ROOT_DIR = "..."` if that default name collides with something your project already has.

```toml
# pyproject.toml
[tool.apiver]
django_settings_module = "config.settings"
```

That last one lets every `apiver` command below skip `--settings` — `apiver` is a standalone CLI, not a
`manage.py` subcommand, so it needs to be told where your settings live one way or another.

### 3. Run `apiver init`

```console
$ uv run apiver init --base v1
wrote .../apiversions/v1/registry.py
wrote .../apiversions/urls.py
wrote .../apiver.toml
```

It found and wrote every existing route — 22 of them — importing your existing views exactly where
they already live. You wrote none of this:

```python
from apiver.drf import Version

from addresses.views import AddressViewSet
from healthz import healthz
from legacy.views import LegacyInvoiceViewSet
from notifications.views import NotificationViewSet, mark_all_read
from orders.views import OrderViewSet, OrdersExportView
from payments.views import PaymentViewSet, PaymentsSummaryView
from users.views import UserViewSet
from webhooks.views import WebhookEndpointViewSet

v1 = Version("v1")
v1.register("addresses", AddressViewSet, basename="addresses")
v1.register("docs/", v1.docs_view(), name="v1-docs")
v1.register("healthz/", healthz, name="healthz")
v1.register("integrations/webhooks", WebhookEndpointViewSet, basename="webhooks")
v1.register("legacy-invoices", LegacyInvoiceViewSet, basename="legacy-invoices")
v1.register("notifications", NotificationViewSet, basename="notifications")
v1.register("notifications/mark-all-read/", mark_all_read, name="notifications-mark-all-read")
v1.register("orders", OrderViewSet, basename="orders")
v1.register("orders/export/", OrdersExportView, name="orders-export")
v1.register("payments", PaymentViewSet, basename="payments")
v1.register("payments/summary/", PaymentsSummaryView, name="payments-summary")
v1.register("users", UserViewSet, basename="users")
v1.register("schema/", v1.schema_view(prefix="api/v1/"), name="v1-schema")
```

### 4. Add one line to your root `urls.py`

```diff
     path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
     path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
+    path("", include("apiversions.urls")),
 ]
```

### That's it

```console
$ uv run python manage.py check
System check identified no issues (0 silenced).
```

Your API is now also live at `/api/v1/...`, serving the exact same views it always did. Nothing moved,
nothing was rewritten — go hit any endpoint you already had and it answers exactly as before, just
under a new, versioned path.

## Ship a breaking change

`v1` is done. Here's the actual payoff: touch only what changed, and leave the rest of the surface
alone.

### 5. Mount `v2`

```diff
-APIVER_VERSIONS = ["v1"]
+APIVER_VERSIONS = ["v1", "v2"]
```

```console
$ uv run apiver mount v2 --from v1
wrote .../apiversions/v2/registry.py
wrote .../apiversions/urls.py
apiver: add 'v2' to APIVER_VERSIONS to make it live.
```

```python
from apiversions.v1.registry import v1

v2 = v1.derive("v2")
v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
v2.override("docs/", v2.docs_view(), name="docs")
```

### 6. Make the change

Say `v2` renames `full_name` to `display_name` on `users`. The override lives right next to the
original — apiver has no opinion on where your code lives, only on where it gets registered:

```python
# users/serializers.py
class UserSerializerV2(UserSerializer):
    display_name = serializers.CharField(source="full_name")

    class Meta(UserSerializer.Meta):
        fields = ["id", "username", "email", "display_name", "is_active"]
```

```python
# users/views.py
class UserViewSetV2(UserViewSet):
    serializer_class = UserSerializerV2
```

One rule: anything you register or override on a version past the base needs that version's name in
its own class name — `UserSerializerV2`, not `UserSerializer`. apiver enforces it the moment you try to
skip it.

Wire it into `apiversions/v2/registry.py`, and drop `legacy-invoices` while you're in there:

```diff
 from apiversions.v1.registry import v1
+
+from users.views import UserViewSetV2
 
 v2 = v1.derive("v2")
 v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
 v2.override("docs/", v2.docs_view(), name="docs")
+v2.override("users", UserViewSetV2, basename="users")
+v2.remove("legacy-invoices")
```

That's `register()`, `override()`, and `remove()` — the whole vocabulary. Renames, removals, nested
restructuring, and every other shape a breaking change takes in practice are cataloged in
[What's Supported](supported.md).

### 7. Regenerate the manifest

```console
$ uv run python manage.py check
WARNINGS:
?: (apiver.W001) .../apiver.toml is stale or missing — run `apiver manifest` to regenerate it.

$ uv run apiver manifest
wrote .../apiver.toml

$ uv run python manage.py check
System check identified no issues (0 silenced).
```

### See it composed

```console
$ uv run apiver versions
v1 (base version) — mutable, live
  routes: 22 defined, 0 inherited

v2 (derived from v1) — mutable, live
  routes: 4 defined, 16 inherited
    defines:  ^docs/\Z
    defines:  ^schema/\Z
    defines:  ^users/$
    defines:  ^users/(?P<pk>[^/.]+)/$
    inherits from v1: ^addresses/$
    inherits from v1: ^orders/$
    inherits from v1: ^payments/$
    inherits from v1: ^integrations/webhooks/$
    ...
```

`v2` defines exactly the 2 routes it changed, plus its own `docs`/`schema`. `legacy-invoices` doesn't
appear anywhere under `v2`. Everything else — orders, payments, webhooks, addresses, notifications — is
inherited from `v1`, unchanged.

### Prove it

Exercised against a migrated dev database:

```pycon
>>> c.get("/api/v1/users/").json()["results"][0]
{'id': 1, 'username': 'ada', 'email': 'ada@example.com', 'full_name': 'Ada Lovelace', 'is_active': True}
>>> c.get("/api/v2/users/").json()["results"][0]
{'id': 1, 'username': 'ada', 'email': 'ada@example.com', 'display_name': 'Ada Lovelace', 'is_active': True}
>>> c.get("/api/v2/legacy-invoices/").status_code
404
>>> c.get("/api/v1/legacy-invoices/").status_code  # v1 unaffected throughout
200
```

## A stable pointer, if you want one

A client-facing name (`stable`, `current`) that should move to a newer version later, without callers
changing their URL, is one command:

```console
$ uv run apiver alias stable --from v2
```

```python
APIVER_ALIASES = ["stable"]
```

Re-pointing it once `v3` ships is a one-line `target=` edit — callers hitting `/api/stable/...` never
see their URL change.

## Not covered here

- **Deprecating a version.** `v1.deprecate(sunset=...)` — the natural next step once `v2` exists and
  clients should start moving off `v1`. See [Version lifecycle](guides/version-lifecycle.md).
- **Hyperlinked serializers.** `HyperlinkedModelSerializer` / `HyperlinkedRelatedField` aren't supported
  yet — using either in an inherited serializer today produces silently wrong-version links. Tracked as
  [#62](https://github.com/edraobdu/apiver/issues/62).
