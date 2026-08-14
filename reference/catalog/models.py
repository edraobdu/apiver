from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=50)


class Product(models.Model):
    """Nested-router spike (see .scratch/nested-routers-spike/): a child
    resource scoped under its parent's pk, `categories/{category_pk}/products/`,
    registered via drf-nested-routers' NestedSimpleRouter — the third-party
    library variant, as opposed to orders/'s hand-rolled prefix."""

    category = models.ForeignKey(Category, related_name="products", on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    price = models.IntegerField()
