from django.db import models


class Order(models.Model):
    reference = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default="open")


class OrderItem(models.Model):
    """A child resource scoped under its parent's pk, `orders/{order_pk}/items/`
    — the single-level nested-router example, registered via a hand-embedded
    lookup regex (no router library needed for this shape either)."""

    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    sku = models.CharField(max_length=50)
    quantity = models.IntegerField(default=1)
