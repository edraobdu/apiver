"""Exercises the project's first relational resource: the FK to users, the
read/write serializer split, the custom postal-code validator, and search."""

import pytest
from rest_framework.test import APIClient

from addresses.models import Address
from users.models import UserProfile


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user():
    return UserProfile.objects.create(username="ada", email="ada@example.com")


@pytest.mark.django_db
def test_create_and_list_returns_nested_user(client, user):
    response = client.post(
        "/api/v1/addresses/",
        {
            "user": user.pk,
            "line1": "1 Infinite Loop",
            "city": "Cupertino",
            "postal_code": "95014",
            "country": "US",
        },
    )
    assert response.status_code == 201

    listed = client.get("/api/v1/addresses/").data["results"][0]
    assert listed["user"]["username"] == "ada"  # AddressReadSerializer nests the user
    assert listed["user"]["email"] == "ada@example.com"


@pytest.mark.django_db
def test_invalid_postal_code_for_country_is_rejected(client, user):
    response = client.post(
        "/api/v1/addresses/",
        {
            "user": user.pk,
            "line1": "1 Infinite Loop",
            "city": "Cupertino",
            "postal_code": "not-a-zip",
            "country": "US",
        },
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_valid_postal_code_per_country(client, user):
    response = client.post(
        "/api/v1/addresses/",
        {
            "user": user.pk,
            "line1": "24 Sussex Dr",
            "city": "Ottawa",
            "postal_code": "K1M 1M4",
            "country": "CA",
        },
    )

    assert response.status_code == 201


@pytest.mark.django_db
def test_search_filters_by_city(client, user):
    Address.objects.create(user=user, line1="1 A St", city="Austin", postal_code="73301", country="US")
    Address.objects.create(user=user, line1="2 B St", city="Boston", postal_code="02101", country="US")

    response = client.get("/api/v1/addresses/?search=Austin")

    results = response.data["results"]
    assert len(results) == 1
    assert results[0]["city"] == "Austin"
