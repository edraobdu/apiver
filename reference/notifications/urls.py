from django.urls import path
from rest_framework.routers import SimpleRouter

from notifications.views import NotificationViewSet, mark_all_read

router = SimpleRouter()
router.register("notifications", NotificationViewSet, basename="notifications")

urlpatterns = [
    # Same swallow hazard as payments/summary (config/urls.py originally, now
    # payments/urls.py): the router's detail regex would otherwise treat
    # "mark-all-read" as a pk. Explicit-before-router, every time, per app.
    path("notifications/mark-all-read/", mark_all_read, name="notifications-mark-all-read"),
] + router.urls
