# Adopting apiver into an existing project

Nothing below assumes a clean starting point. Whatever your project's API looks like today — one
version or a dozen, a consistent scheme or several abandoned ones, hand-rolled `if request.version`
branches you'd rather not think about — apiver doesn't ask you to sort any of that out first. It adopts
your project's current, live routes as the **Base Version**, exactly where they already are, and from
that point on your *next* version is the first one apiver actually manages. Everything before it stays
exactly as it was.

This walks a project that already has a working DRF API through adopting apiver: installing it,
running `apiver init` to adopt the existing API as the Base Version, then authoring and mounting a
second version as a Delta. Every step below was actually run against `reference/` (issue #22) —
commands, output and generated code are real, not illustrative. `reference/` itself is kept out of
version control on purpose, so it stays a clean "before" fixture; run this yourself against a
fresh checkout to reproduce it.

Run every command from `reference/`, using `uv run` (or an activated `.venv`).

## Prerequisites

- `django~=5.2`, `djangorestframework~=3.18`, `drf-spectacular~=0.30`.
- An API reachable by walking `ROOT_URLCONF`: plain `path()` entries, router-registered ViewSets
  with explicit `basename=`, at most one drf-spectacular `SpectacularAPIView`. `apiver init`
  refuses anything it can't classify — see "If init refuses" below.

## 1. Install apiver

```diff
 dependencies = [
     "django~=5.2",
     "djangorestframework~=3.18",
     "drf-spectacular~=0.30",
+    "apiver",
 ]
 
 [dependency-groups]
 dev = [
     "pytest>=8.0",
     "pytest-django>=4.9",
 ]
+
+[tool.uv.sources]
+apiver = { path = "..", editable = true }
```

```console
$ uv sync
Resolved 25 packages in 394ms
   Building apiver @ file:///.../apiver
Installed 1 package in 1ms
 ~ apiver==0.1.0.dev0 (from file:///.../apiver)
```

`reference/pyproject.toml` already pins `django~=5.2` to match apiver's own supported range — a
mismatch here fails at `uv sync`, not at any apiver command.

Add `"apiver"` to `config/settings.py`'s `INSTALLED_APPS` — it has no models, but its system
checks (layout, manifest freshness, max-live-versions) only register via `AppConfig.ready()`:

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

## 2. Add the three settings, and skip repeating `--settings`

At the bottom of `config/settings.py`:

```python
APIVER_ROOT_DIR = "api"  # dotted path to the package holding every version
APIVER_ROOT_PREFIX = "api/"  # absolute URL path every version mounts under
APIVER_VERSIONS = ["v1"]  # hand-maintained list of Live version names
# APIVER_VERSION_SCHEME = "sequential"  # or "semver"/"date"; this is the default, shown for
# discoverability — --base (and later, apiver mount's version name) is validated against it.
```

`reference/`'s whole pre-existing API already lives under `api/`, which is why no `--prefix`
override is needed below — `APIVER_ROOT_PREFIX` already names it. (`APIVER_ROOT_PREFIX` is only
about where the *new* versioned surface mounts, not where existing code lives today — if those
differ, `apiver init --prefix <path>` says so explicitly. `--prefix` is repeatable
(`--prefix api/ --prefix legacy/`) for a project whose routes are scattered across several
unrelated ancestors — every route under any of them is adopted together, keyed relative to
whichever prefix it fell under. Overlapping values, including passing the same one twice, are
refused rather than silently deduped.)

`apiver` is a standalone CLI, not a `manage.py` subcommand, so it needs Django settings resolved
one way or another. Rather than passing `--settings` (or exporting `DJANGO_SETTINGS_MODULE`) on
every single command below, set it once:

```diff
 [tool.uv.sources]
 apiver = { path = "..", editable = true }
+
+[tool.apiver]
+django_settings_module = "config.settings"
```

Every `apiver` command checked `--settings`, then the env var, then this, in that order — so this
is a project-local default, always overridable. (`manage.py` needs no equivalent: it already sets
`DJANGO_SETTINGS_MODULE` itself via `os.environ.setdefault`.)

## 3. Run `apiver init`

```console
$ uv run apiver init --base v1
wrote .../reference/api/v1/registry.py
wrote .../reference/api/urls.py
wrote .../reference/apiver.toml
```

`--base v1` is the name `init` adopts the existing project as — a one-shot input for this single
invocation, not a setting: `init` writes `registry.py` once and never regenerates it.

`api/v1/registry.py` is generated in full — every pre-existing resource (`addresses`,
`legacy-invoices`, `notifications` plus its `mark-all-read` action, `orders` plus its CSV export,
`payments` plus its summary view, `users`, `webhooks`) becomes one `register()` call, importing
the existing views exactly where they already lived:

```python
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

`api/urls.py` — the Aggregation Root — mounts it:

```python
from api.v1.registry import v1

urlpatterns = [
    path("api/v1/", include(v1.urls)),
]
```

Point the project's real root `urls.py` at it — one appended `include()`, nothing else changes:

```diff
     path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
     path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
+    # apiver's Aggregation Root, appended, not substituted: everything above
+    # stays exactly where it was before adopting apiver.
+    path("", include("api.urls")),
 ]
```

The new surface lives at `/api/v1/...`, reaching the same handlers a second way. The old,
unversioned paths keep serving exactly as before — retiring them is a separate decision, not a
side effect of `init`.

**Schema/docs get version-qualified names automatically.** A bare `schema`/`docs` name on the Base
Version would collide with the pre-existing, identically-named routes kept mounted alongside it —
Django's `reverse()` would silently pick whichever was registered last. So the discovered schema
view is always named `f"{base_name}-schema"` and the docs view's `url_name` is repointed at it,
regardless of what they were called before — shown above (`v1-schema`, `v1-docs`).

### If init refuses

`init` writes nothing and reports every offending route at once. Common causes: a ViewSet mounted
without explicit `basename=`; a handler with no importable symbol (built in a closure/decorator
without `functools.wraps`); `re_path()` instead of `path()`; a namespaced `include()` or
`i18n_patterns()` at the root; more than one drf-spectacular schema view under the prefix. Register
any of these by hand instead — `init` covers the common case, not every case. `reference/` never
triggers any of them.

## 4. Verify the base version

```console
$ uv run python manage.py check
System check identified no issues (0 silenced).

$ uv run pytest -q
25 passed, 3 warnings in 0.34s
```

All 25 pre-existing tests pass **unmodified** — they hit the original, unversioned paths, which
`init` never touched.

## 5. Mount v2

```diff
-APIVER_VERSIONS = ["v1"]
+APIVER_VERSIONS = ["v1", "v2"]
```

```console
$ uv run apiver mount v2 --from v1
wrote .../reference/api/v2/registry.py
wrote .../reference/api/urls.py
apiver: add 'v2' to APIVER_VERSIONS to make it live.
```

`mount` never touches `settings.py` itself — that's the reminder above; skip it and the version
silently fails to resolve. The generated `api/v2/registry.py` is deliberately minimal:

```python
from api.v1.registry import v1

v2 = v1.derive("v2")
v2.override("schema/", v2.schema_view(prefix="api/v2/"), name="schema")
v2.override("docs/", v2.docs_view(), name="docs")
```

Both use `override()` because `init` already wired `schema/`/`docs/` on v1 — `mount` uses
`register()` only when deriving from a version that doesn't already have one. No hand-written
Swagger/Redoc subclass is needed here either — `docs_view()` resolves the right, namespaced schema
route for whichever version calls it.

## 6. Author the breaking changes

This is the part `mount` never does for you — the six catalogue rows (issue #22's "awkward or
schema-invisible" set) landing on `reference/`'s existing `users`/`orders`/`payments`/`webhooks`/
`legacy-invoices` resources.

Class-based handlers registered or overridden on a non-base version must carry the version's name,
uppercased, in their class name (`PaymentSerializerV2`, not `PaymentSerializer`) — enforced at
`register()`/`override()` time, because drf-spectacular names schema components off
`__class__.__name__` alone, and two same-named classes in different versions would collide. This
applies even to a handler that's otherwise unchanged (only its URL moved, or it's a third-party
class you don't own) — subclass it trivially just to carry the suffix.

Create `api/v2/serializers.py`:

```python
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from orders.serializers import OrderSerializer
from payments.serializers import PaymentSerializer
from users.serializers import UserSerializer


class CardSchemaV2(serializers.Serializer):
    """Not registered anywhere — exists only so `@extend_schema_field` below can
    give `card` a proper nested-object schema instead of drf-spectacular's opaque
    string fallback for a SerializerMethodField it can't infer a return type for."""

    last4 = serializers.CharField()
    brand = serializers.CharField()


class UserSerializerV2(UserSerializer):
    """V2 renames `full_name` to `display_name` (catalogue row 5) — the field-add
    + field-remove idiom; there is no dedicated rename primitive. A schema diff
    between v1 and v2 reports this as one field deleted, one added, even though
    it's the same underlying attribute."""

    display_name = serializers.CharField(source="full_name")

    class Meta(UserSerializer.Meta):
        fields = ["id", "username", "email", "display_name", "is_active"]


class OrderSerializerV2(OrderSerializer):
    """V2 drops `status` entirely (catalogue row 6) — Meta.fields surgery, the
    canonical removal idiom. `status = None` would raise: apiver refuses that
    shortcut outright rather than leaving it to silently survive."""

    class Meta(OrderSerializer.Meta):
        fields = [name for name in OrderSerializer.Meta.fields if name != "status"]


class PaymentSerializerV2(PaymentSerializer):
    """Two independent V2 changes on the same resource:

    - `card_last4`/`card_brand` collapse into a nested `card` object (catalogue
      row 9, flat<->nested restructuring) — the flat fields drop out of
      Meta.fields, a SerializerMethodField assembles the nested read shape, and
      create/update translate the nested write shape back to the two flat model
      fields by hand.
    - `get_display_amount`'s output format changes (catalogue row 10) — still a
      SerializerMethodField, so this produces *no* schema delta at all; the only
      way to catch it is to call the endpoint and read the body.
    """

    card = serializers.SerializerMethodField()

    class Meta(PaymentSerializer.Meta):
        fields = ["id", "amount", "currency", "status", "card", "display_amount", "created_at"]

    @extend_schema_field(CardSchemaV2)
    def get_card(self, obj):
        return {"last4": obj.card_last4, "brand": obj.card_brand}

    def get_display_amount(self, obj):
        return f"${obj.amount / 100:.2f}"

    def _card_fields(self):
        card = self.initial_data.get("card") or {}
        return {"card_last4": card.get("last4", ""), "card_brand": card.get("brand", "")}

    def create(self, validated_data):
        validated_data.update(self._card_fields())
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "card" in self.initial_data:
            validated_data.update(self._card_fields())
        return super().update(instance, validated_data)
```

Create `api/v2/views.py`:

```python
from orders.views import OrderViewSet
from payments.views import PaymentViewSet
from users.views import UserViewSet
from webhooks.views import WebhookEndpointViewSet

from .serializers import OrderSerializerV2, PaymentSerializerV2, UserSerializerV2


class UserViewSetV2(UserViewSet):
    serializer_class = UserSerializerV2


class OrderViewSetV2(OrderViewSet):
    serializer_class = OrderSerializerV2


class PaymentViewSetV2(PaymentViewSet):
    """`refund` drops out entirely (catalogue row 14b). `refund = None` is the
    correct idiom here — DRF's `get_extra_actions()` reads the class attribute at
    router-registration time and simply omits a `None`d action, unlike the
    `field = None` footgun on a serializer."""

    serializer_class = PaymentSerializerV2
    refund = None


class WebhookEndpointViewSetV2(WebhookEndpointViewSet):
    """Behavior is unchanged — exists only so the URL-prefix move (catalogue row
    13, below) has a version-suffixed class to register at the new key. apiver's
    suffix rule applies even to a class whose only change is where it's mounted —
    there's no "reuse the parent's class unchanged" escape hatch."""
```

Then extend the `api/v2/registry.py` `mount` already wrote — add resource-level changes below the
two lines already there:

```diff
 from api.v1.registry import v1
 
+from .views import (
+    OrderViewSetV2,
+    PaymentViewSetV2,
+    UserViewSetV2,
+    WebhookEndpointViewSetV2,
+)
+
 v2 = v1.derive('v2')
 v2.override('schema/', v2.schema_view(prefix='api/v2/'), name='schema')
 v2.override('docs/', v2.docs_view(), name='docs')
+
+# Field rename (row 5), field removal (row 6), and the combined nested-restructure
+# + SerializerMethodField-output-change resource (rows 9, 10) — see
+# api/v2/serializers.py. @action removal (row 14b) — see api/v2/views.py.
+v2.override("users", UserViewSetV2, basename="users")
+v2.override("orders", OrderViewSetV2, basename="orders")
+v2.override("payments", PaymentViewSetV2, basename="payments")
+
+# Whole-resource removal (row 12) — legacy-invoices does not exist in v2 or later.
+v2.remove("legacy-invoices")
+
+# URL prefix change (row 13) — no first-class "move" primitive: remove the old
+# key, register the same (version-suffixed) handler under the new one.
+v2.remove("integrations/webhooks")
+v2.register("webhooks", WebhookEndpointViewSetV2, basename="webhooks")
```

`override()` replaces the whole registration — no partial override, so a narrower one drops any
parent routes it doesn't re-declare. `remove()` only stops this version (and its descendants) from
serving a key; the parent is unaffected.

## 7. Verify again

```console
$ uv run python manage.py check
System check identified some issues:
WARNINGS:
?: (apiver.W001) .../apiver.toml is stale or missing — run `apiver manifest` to regenerate it.

$ uv run apiver manifest
wrote .../reference/apiver.toml

$ uv run python manage.py check
System check identified no issues (0 silenced).

$ uv run pytest -q
25 passed, 3 warnings in 0.34s
```

The 25 pre-existing tests still pass unmodified — v1's surface is untouched by any of this.
`apiver versions` confirms the composition without booting the project at all:

```console
$ uv run apiver versions
v1 (base version) — mutable, live
  routes: 22 defined, 0 inherited
    ...
v2 (derived from v1) — mutable, live
  routes: 11 defined, 8 inherited
    defines:  ^docs/\Z
    defines:  ^orders/$
    defines:  ^orders/(?P<pk>[^/.]+)/$
    defines:  ^payments/$
    defines:  ^payments/(?P<pk>[^/.]+)/$
    defines:  ^schema/\Z
    defines:  ^users/$
    defines:  ^users/(?P<pk>[^/.]+)/$
    defines:  ^webhooks/$
    defines:  ^webhooks/(?P<pk>[^/.]+)/$
    defines:  ^webhooks/(?P<pk>[^/.]+)/test-delivery/$
    inherits from v1: ^addresses/$
    inherits from v1: ^addresses/(?P<pk>[^/.]+)/$
    ...
```

v2 defines exactly the 3 overridden resources plus `webhooks` at its new prefix and its own
`docs`/`schema`; `legacy-invoices` and `integrations/webhooks` don't appear under v2 at all.
Everything else (`addresses`, `notifications`, `healthz`) is inherited from v1 unchanged.

### Confirming each row actually works, not just composes

`manage.py check` proves the routing composes; it says nothing about response bodies. Exercised by
hand against a migrated dev database:

```pycon
>>> c.get("/api/v2/users/").json()["results"][0]
{'id': 1, 'username': 'ada', 'email': 'ada@example.com', 'display_name': 'Ada Lovelace', 'is_active': True}
>>> c.get("/api/v2/orders/").json()["results"][0]
{'id': 1, 'reference': 'ORD-1'}                          # no 'status'
>>> c.get("/api/v2/payments/").json()["results"][0]
{'id': 1, 'amount': 1050, 'currency': 'USD', 'status': 'pending',
 'card': {'last4': '4242', 'brand': 'visa'}, 'display_amount': '$10.50', 'created_at': '...'}
>>> c.get("/api/v2/legacy-invoices/").status_code
404
>>> c.get("/api/v2/integrations/webhooks/").status_code
404
>>> c.get("/api/v2/webhooks/").status_code
200
>>> c.post("/api/v2/payments/1/refund/").status_code
404
>>> c.get("/api/v1/users/").json()["results"][0]  # v1 unaffected throughout
{'id': 1, 'username': 'ada', 'email': 'ada@example.com', 'full_name': 'Ada Lovelace', 'is_active': True}
```

## 8. Naming a stable pointer (optional)

A client-facing name (`stable`, `current`) that should move to a different version later, without
callers changing their URL, is an `Alias`, not another mounted version:

```console
$ uv run apiver alias stable --from v2
```

Writes no `registry.py` of its own — `Alias.schema_view()`/`docs_view()` proxy straight through to
the target's, so re-pointing it later is a one-line `target=` edit. Like `mount`, never touches
`settings.py`:

```python
APIVER_ALIASES = ["stable"]
```

## Not covered here

- **Deprecating a version** (`Version.deprecate(sunset=...)`) — outside issue #22's six-row
  catalogue scope; a natural next exercise against this same `reference/` state.
- **Hyperlinked serializers and version-aware `reverse()`.** `HyperlinkedModelSerializer`/
  `HyperlinkedRelatedField` aren't demonstrated because they aren't supported yet: the design is
  accepted (`docs/adr/0005-intra-version-hyperlinking.md`) but unimplemented — no `apiver.reverse`,
  no request-stamping, no `get_url` patch exist in the library today. Using either in an inherited
  serializer currently produces silently wrong-version links. Tracked as
  [#62](https://github.com/edraobdu/apiver/issues/62).
