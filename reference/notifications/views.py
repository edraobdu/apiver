from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from notifications.models import Notification
from notifications.pagination import NotificationCursorPagination
from notifications.serializers import NotifSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by("-created_at")
    serializer_class = NotifSerializer
    pagination_class = NotificationCursorPagination
    # A future version tightening this to, say, "3/minute" changes behavior with
    # zero schema delta — same diff-blind shape as permissions (catalogue row 20).
    throttle_classes = [UserRateThrottle]


@api_view(["POST"])
def mark_all_read(request):
    """Plain function view, not a viewset action — proves non-viewset routes compose
    just as well as router-registered ones, same lesson as healthz/payments-summary."""
    updated = Notification.objects.filter(read=False).update(read=True)
    return Response({"marked": updated})
