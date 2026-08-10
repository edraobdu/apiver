"""Prints the plain-serializer payloads with and without the patch. Run with -s."""

import json

import pytest
from rest_framework.test import APIClient

from payments.models import Payment
from spike import zero_pain

pytestmark = [pytest.mark.django_db, pytest.mark.urls("spike.urls")]

PATHS = ["/api/v1/plain-payments/", "/api/v2/plain-payments/", "/api/stable/plain-payments/"]


def _dump(label):
    client = APIClient()
    print(f"\n===== {label} =====")
    for path in PATHS:
        body = client.get(path).data["results"][0]
        print(f"\nGET {path}\n{json.dumps(body, indent=2, default=str)}")


def test_capture_zero_pain():
    Payment.objects.create(amount=1050, currency="USD")
    try:
        _dump("PLAIN DRF SERIALIZER — apiver patch NOT installed")
        zero_pain.install()
        _dump("SAME SERIALIZER, UNCHANGED — apiver patch installed")
    finally:
        zero_pain.uninstall()
