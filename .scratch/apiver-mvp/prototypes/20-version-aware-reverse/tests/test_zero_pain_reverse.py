"""Closing the bare-reverse() residue: a ContextVar, and an import-order gamble.

The `url` field is already free (test_zero_pain.py). What remains is `reverse()` called
directly in developer code — in a SerializerMethodField, a view, a model method.
"""

import importlib
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from rest_framework.test import APIClient

from payments.models import Payment
from spike import zero_pain
from spike.apiver_core import apiver_reverse, current_version

pytestmark = [pytest.mark.django_db, pytest.mark.urls("spike.urls")]


@pytest.fixture
def fully_patched():
    zero_pain.install()
    zero_pain.install_reverse_patch()
    yield
    zero_pain.uninstall_reverse_patch()
    zero_pain.uninstall()


# -- the ContextVar closes the "no request" hole -------------------------------


def test_reverse_with_no_request_now_follows_the_serving_version():
    """Previously fell back to the Base Version. The ContextVar fixes it."""
    from spike.v2.registry import v2

    token = current_version.set(v2)
    try:
        url = apiver_reverse("payments-detail", kwargs={"pk": 1}, request=None)
    finally:
        current_version.reset(token)

    assert url == "/api/v2/payments/1/"


def test_outside_any_request_it_still_falls_back_to_the_base_version():
    """A Celery task or management command has no context — documented, not fixed."""
    assert apiver_reverse("payments-detail", kwargs={"pk": 1}, request=None) == (
        "/api/v1/payments/1/"
    )


def test_the_contextvar_is_reset_after_each_request(client_and_payment):
    client, _ = client_and_payment

    client.get("/api/v2/payments/")

    assert current_version.get() is None


def test_the_contextvar_does_not_leak_across_threads():
    """ContextVar rather than threading.local — each worker sees only its own version."""

    def fetch(path):
        return path, APIClient().get(path).data["stamped_on_request"]

    paths = ["/api/v1/payments/whoami/", "/api/v2/payments/whoami/"] * 40
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(fetch, paths))

    for path, reported in results:
        assert reported == ("v1" if "/v1/" in path else "v2")
    assert current_version.get() is None


# -- the import-order gamble ---------------------------------------------------


def test_a_module_imported_before_the_patch_keeps_the_original_reverse():
    """`from x import y` binds early. This is the failure mode of patching a module attr."""
    sys.modules.pop("spike.late_import_probe", None)
    probe = importlib.import_module("spike.late_import_probe")  # imported first

    zero_pain.install_reverse_patch()
    try:
        from spike.v2.registry import v2

        token = current_version.set(v2)
        try:
            assert probe.build_link(1) == "/api/v1/plain-payments/1/"  # patch missed it
        finally:
            current_version.reset(token)
    finally:
        zero_pain.uninstall_reverse_patch()


def test_a_module_imported_after_the_patch_picks_it_up():
    """Which is why apiver would have to patch during app loading, before urls.py runs."""
    zero_pain.install_reverse_patch()
    try:
        sys.modules.pop("spike.late_import_probe", None)
        probe = importlib.import_module("spike.late_import_probe")  # imported second

        from spike.v2.registry import v2

        token = current_version.set(v2)
        try:
            assert probe.build_link(1) == "/api/v2/plain-payments/1/"  # patch took
        finally:
            current_version.reset(token)
    finally:
        zero_pain.uninstall_reverse_patch()
        sys.modules.pop("spike.late_import_probe", None)


# -- end to end, with everything installed -------------------------------------


def test_fully_patched_plain_serializer_is_correct_in_both_fields(client_and_payment):
    """`spike/plain/serializers.py` imported reverse at module load, long before the
    patch — so this shows what a real project gets, not a staged best case."""
    client, payment = client_and_payment
    zero_pain.install()
    zero_pain.install_reverse_patch()
    try:
        row = client.get("/api/v2/plain-payments/").data["results"][0]
    finally:
        zero_pain.uninstall_reverse_patch()
        zero_pain.uninstall()

    assert "/api/v2/plain-payments/" in row["url"]
    assert "/api/v1/plain-payments/" in row["receipt_link"]  # early import, still missed


def test_realistic_deployment_ordering_fixes_both_fields(client_and_payment):
    """The ordering a real project actually gets.

    Django imports app configs and runs `ready()` during `django.setup()`; the ROOT_URLCONF
    — and therefore the developer's views and serializers — is imported later, on first
    resolve. So apiver patching in `ready()` lands *before* `from rest_framework.reverse
    import reverse` runs in user code. Simulated here by reimporting the serializer module
    after the patch and rebinding it onto the viewset.
    """
    client, payment = client_and_payment
    from spike.plain.views import PlainPaymentViewSet

    original_serializer = PlainPaymentViewSet.serializer_class

    zero_pain.install()
    zero_pain.install_reverse_patch()
    sys.modules.pop("spike.plain.serializers", None)
    reimported = importlib.import_module("spike.plain.serializers")
    PlainPaymentViewSet.serializer_class = reimported.PlainPaymentSerializer
    try:
        row = client.get("/api/v2/plain-payments/").data["results"][0]
    finally:
        PlainPaymentViewSet.serializer_class = original_serializer
        zero_pain.uninstall_reverse_patch()
        zero_pain.uninstall()
        sys.modules.pop("spike.plain.serializers", None)

    assert f"/api/v2/plain-payments/{payment.pk}/" in row["url"]
    assert f"/api/v2/plain-payments/{payment.pk}/" in row["receipt_link"]


def test_django_urls_reverse_is_out_of_reach(fully_patched):
    """No request, no self, and shared with the admin — nothing safe to intercept."""
    from django.urls import reverse as django_reverse

    from spike.v2.registry import v2

    token = current_version.set(v2)
    try:
        assert django_reverse("payment-detail", kwargs={"pk": 1}) == (
            "/api/v1/plain-payments/1/"
        )
    finally:
        current_version.reset(token)


@pytest.fixture
def client_and_payment():
    return APIClient(), Payment.objects.create(amount=1050, currency="USD")
