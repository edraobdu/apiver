"""Exercises the custom CSV renderer and its explicit-before-router mount."""

import pytest
from rest_framework.test import APIClient

from orders.models import Order


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
def test_export_route_is_not_swallowed_by_the_orders_detail_pattern(client):
    Order.objects.create(reference="ORD-1", status="open")

    response = client.get("/api/v1/orders/export/", HTTP_ACCEPT="text/csv")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_export_renders_valid_csv_rows(client):
    Order.objects.create(reference="ORD-1", status="open")
    Order.objects.create(reference="ORD-2", status="shipped")

    response = client.get("/api/v1/orders/export/", HTTP_ACCEPT="text/csv")

    body = response.content.decode()
    lines = body.strip().split("\n")
    assert lines[0] == "id,reference,status"
    assert "ORD-1,open" in lines[1]
    assert "ORD-2,shipped" in lines[2]
