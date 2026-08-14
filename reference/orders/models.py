from django.db import models


class Order(models.Model):
    reference = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default="open")


class OrderItem(models.Model):
    """Nested-router spike (see .scratch/nested-routers-spike/): a child
    resource scoped under its parent's pk, `orders/{order_pk}/items/`,
    registered via a hand-embedded lookup regex — no router library."""

    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    sku = models.CharField(max_length=50)
    quantity = models.IntegerField(default=1)
