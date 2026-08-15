"""Deeper nested-router shapes: two siblings (products, collections) under
one parent, and a third level (reviews) under one of them."""

import pytest
from rest_framework.test import APIClient

from catalog.models import Category, Product


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def category():
    return Category.objects.create(name="Widgets")


@pytest.mark.django_db
def test_products_and_collections_are_independent_siblings_under_one_category(client, category):
    other_category = Category.objects.create(name="Gadgets")

    client.post(f"/api/categories/{category.pk}/products/", {"name": "Sprocket", "price": "9.99"})
    client.post(f"/api/categories/{other_category.pk}/products/", {"name": "Cog", "price": "1.00"})
    client.post(f"/api/categories/{category.pk}/collections/", {"name": "Summer"})

    products = client.get(f"/api/categories/{category.pk}/products/").data["results"]
    collections = client.get(f"/api/categories/{category.pk}/collections/").data["results"]

    assert [p["name"] for p in products] == ["Sprocket"]
    assert [c["name"] for c in collections] == ["Summer"]


@pytest.mark.django_db
def test_reviews_nest_a_third_level_under_product(client, category):
    product_response = client.post(
        f"/api/categories/{category.pk}/products/", {"name": "Sprocket", "price": "9.99"}
    )
    product_id = product_response.data["id"]

    other_product = Product.objects.create(category=category, name="Cog", price="1.00")

    client.post(
        f"/api/categories/{category.pk}/products/{product_id}/reviews/",
        {"rating": 5, "comment": "Great!"},
    )

    reviews = client.get(f"/api/categories/{category.pk}/products/{product_id}/reviews/").data["results"]
    other_reviews = client.get(f"/api/categories/{category.pk}/products/{other_product.pk}/reviews/").data[
        "results"
    ]

    assert [r["rating"] for r in reviews] == [5]
    assert other_reviews == []
