from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)


class Product(models.Model):
    """Nested under its category — `categories/{category_pk}/products/`,
    one of two siblings this app demonstrates under the same parent."""

    category = models.ForeignKey(Category, related_name="products", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)


class Collection(models.Model):
    """The sibling to Product under the same parent —
    `categories/{category_pk}/collections/`."""

    category = models.ForeignKey(Category, related_name="collections", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)


class Review(models.Model):
    """A third level, nested under Product —
    `categories/{category_pk}/products/{product_pk}/reviews/`."""

    product = models.ForeignKey(Product, related_name="reviews", on_delete=models.CASCADE)
    rating = models.IntegerField()
    comment = models.CharField(max_length=200, blank=True, default="")
