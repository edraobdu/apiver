from rest_framework.pagination import CursorPagination


class NotificationCursorPagination(CursorPagination):
    """Distinct from the project-wide `PageNumberPagination` default (settings.py) —
    a real codebase rarely settles on one pagination style everywhere, and a future
    version changing *this* class's `page_size` produces no schema delta at all
    (catalogue row 16), same diff-blind shape as payments' default ordering."""

    page_size = 5
    ordering = "-created_at"
