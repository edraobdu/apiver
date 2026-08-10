"""Not an assertion suite — prints the real payloads so the prototype's findings can be
read rather than inferred from green checkmarks. Run with `-s`."""

import json

import pytest
from rest_framework.test import APIClient

from payments.models import Payment

pytestmark = [pytest.mark.django_db, pytest.mark.urls("spike.urls")]


def test_capture():
    client = APIClient()
    Payment.objects.create(amount=1050, currency="USD")

    for path in [
        "/api/v1/payments/",
        "/api/v2/payments/",
        "/api/stable/payments/",
        "/api/v1/naive-payments/",
        "/api/v2/naive-payments/",
    ]:
        body = client.get(path).data["results"][0]
        print(f"\nGET {path}\n{json.dumps(body, indent=2, default=str)}")

    for path in ["/api/v1/payments/whoami/", "/api/v2/payments/whoami/",
                 "/api/stable/payments/whoami/"]:
        print(f"\nGET {path}\n{json.dumps(client.get(path).data, indent=2)}")
