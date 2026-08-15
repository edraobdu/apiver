"""Single-level nested router: orders/{order_pk}/items/, hand-embedded lookup
regex, no router library."""

import pytest
from rest_framework.test import APIClient

from orders.models import Order, OrderItem


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def order():
    return Order.objects.create(reference="ORD-1", status="open")


@pytest.mark.django_db
def test_create_and_list_items_scoped_to_the_order(client, order):
    other_order = Order.objects.create(reference="ORD-2", status="open")
    OrderItem.objects.create(order=other_order, sku="OTHER-SKU", quantity=1)

    response = client.post(f"/api/orders/{order.pk}/items/", {"sku": "WIDGET", "quantity": 3})
    assert response.status_code == 201

    listed = client.get(f"/api/orders/{order.pk}/items/").data["results"]
    assert [item["sku"] for item in listed] == ["WIDGET"]


@pytest.mark.django_db
def test_created_item_is_scoped_to_the_url_order_not_a_posted_one(client, order):
    other_order = Order.objects.create(reference="ORD-2", status="open")

    response = client.post(
        f"/api/orders/{order.pk}/items/", {"order": other_order.pk, "sku": "WIDGET", "quantity": 1}
    )

    assert response.status_code == 201
    assert response.data["order"] == str(order.pk)
