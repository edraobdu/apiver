from drf_spectacular.views import SpectacularSwaggerView

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
    correct, unadorned idiom — DRF's `get_extra_actions()` reads the class
    attribute at router-registration time and simply omits a `None`d action, no
    crash and no silent survival, unlike `field = None`'s footgun on a
    serializer (ADR 0006)."""

    serializer_class = PaymentSerializerV2
    refund = None


class WebhookEndpointViewSetV2(WebhookEndpointViewSet):
    """Behavior is unchanged — this class exists only so the URL-prefix move
    (catalogue row 13, `api/v2/integrations/webhooks/` -> `api/v2/webhooks/`) has
    a version-suffixed class to register at the new key. apiver's suffix rule
    (ADR 0003 item 2) applies to every class-based handler on an authored
    version, even one whose only change is where it's mounted — there's no
    "reuse the parent's class unchanged" escape hatch, by design."""


class SpectacularSwaggerViewV2(SpectacularSwaggerView):
    """Same rule as above, for a third-party class this project doesn't own:
    reused unmodified, subclassed only to satisfy the suffix check. `url_name`
    is pinned explicitly to the namespaced route name — v2 is mounted under the
    Django instance namespace "v2" (ADR 0002 item 7), so the bare "schema" name
    v1 resolves by default would not otherwise be guaranteed to resolve to
    *this* version's schema route."""

    url_name = "v2:schema"
