from django.apps import AppConfig


class ApiverConfig(AppConfig):
    """Registers apiver's Django system checks.

    A project adopting apiver adds `"apiver"` to `INSTALLED_APPS` for no
    other reason than this: `ready()` is Django's own idiomatic hook for
    getting a check onto the registry before `manage.py check`/CI ever runs,
    without depending on some other module (e.g. a URLconf) having been
    imported first (ADR 0003 item 2).
    """

    name = "apiver"

    def ready(self) -> None:
        from .drf import checks  # noqa: F401
        from .drf.hyperlinks import patch_hyperlinked_related_field

        patch_hyperlinked_related_field()
