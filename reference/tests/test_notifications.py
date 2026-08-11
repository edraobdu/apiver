"""Exercises the distinct pagination style, the throttle class being attached, and
the non-viewset bulk-action route (with its own explicit-before-router hazard)."""

import pytest
from rest_framework.test import APIClient

from notifications.models import Notification
from notifications.views import NotificationViewSet
from users.models import UserProfile


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user():
    return UserProfile.objects.create(username="ada", email="ada@example.com")


def test_throttle_class_is_attached():
    """The seed itself (catalogue row 20) — not exercising a 429, which would make
    this suite's pass/fail depend on how many other tests ran first."""
    assert NotificationViewSet.throttle_classes


@pytest.mark.django_db
def test_pagination_uses_the_distinct_cursor_style_not_the_project_default(client, user):
    for i in range(7):
        Notification.objects.create(user=user, verb=f"event.{i}")

    response = client.get("/api/notifications/")

    assert response.status_code == 200
    # CursorPagination's response shape ("next"/"previous", no "count") is the
    # visible proof this isn't the project-wide PageNumberPagination default.
    assert set(response.data.keys()) == {"next", "previous", "results"}
    assert len(response.data["results"]) == 5  # NotificationCursorPagination.page_size


@pytest.mark.django_db
def test_mark_all_read_updates_every_unread_notification(client, user):
    Notification.objects.create(user=user, verb="order.created", read=False)
    Notification.objects.create(user=user, verb="order.shipped", read=False)
    Notification.objects.create(user=user, verb="order.delivered", read=True)

    response = client.post("/api/notifications/mark-all-read/")

    assert response.status_code == 200
    assert response.data == {"marked": 2}
    assert Notification.objects.filter(read=False).count() == 0


@pytest.mark.django_db
def test_mark_all_read_route_is_not_swallowed_by_the_detail_pattern(client, user):
    """Same hazard class as payments/summary and orders/export, now proven for a
    plain function view sitting in front of a SimpleRouter instead of a ViewSet
    action in front of a Default/SimpleRouter."""
    response = client.post("/api/notifications/mark-all-read/")

    assert response.status_code == 200
    assert "marked" in response.data
