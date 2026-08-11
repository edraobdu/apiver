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
v1.register('docs/', SpectacularSwaggerView, name='docs')
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
v1.register('schema/', v1.schema_view(prefix='api/v1/'), name='schema')
