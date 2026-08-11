"""Generated once by `apiver migrate`; hand-editable afterwards, like
Django's own `startapp` boilerplate — it is not regenerated on later
runs (ADR 0003 item 4).
"""

from apiver.drf import Version

from addresses.views import AddressViewSet
from drf_spectacular.views import SpectacularSwaggerView
from healthz import healthz
from legacy.views import LegacyInvoiceViewSet
from notifications.views import NotificationViewSet, mark_all_read
from orders.views import OrderViewSet, OrdersExportView
from payments.views import PaymentViewSet, PaymentsSummaryView
from users.views import UserViewSet
from webhooks.views import WebhookEndpointViewSet

v1 = Version('v1')
v1.register('addresses', AddressViewSet, basename='addresses')
# Renamed by hand from the names `apiver migrate` discovered ('docs'/'schema') —
# this project keeps its pre-existing, unversioned api/docs/ and api/schema/
# mounted too (adoption is additive, not a replacement), and the Base Version's
# bare, unnamespaced route names (ADR 0001 item 4) would otherwise collide with
# those pre-existing same-named routes. Nothing else in this project ever
# reverse()s a route by name, so only the two views that actually call reverse()
# at request time — schema and docs — need distinct names to stay unambiguous.
v1.register('docs/', SpectacularSwaggerView.as_view(url_name='v1-schema'), name='v1-docs')
v1.register('healthz/', healthz, name='healthz')
v1.register('integrations/webhooks', WebhookEndpointViewSet, basename='webhooks')
v1.register('legacy-invoices', LegacyInvoiceViewSet, basename='legacy-invoices')
v1.register('notifications', NotificationViewSet, basename='notifications')
v1.register('notifications/mark-all-read/', mark_all_read, name='notifications-mark-all-read')
v1.register('orders', OrderViewSet, basename='orders')
v1.register('orders/export/', OrdersExportView, name='orders-export')
v1.register('payments', PaymentViewSet, basename='payments')
v1.register('payments/summary/', PaymentsSummaryView, name='payments-summary')
v1.register('users', UserViewSet, basename='users')
v1.register('schema/', v1.schema_view(prefix='api/v1/'), name='v1-schema')
