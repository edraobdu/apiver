from django.db import models

EVENT_TYPE_CHOICES = [
    ("payment.completed", "Payment completed"),
    ("order.created", "Order created"),
    ("order.cancelled", "Order cancelled"),
]


class WebhookEndpoint(models.Model):
    target_url = models.URLField()
    event_type = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES)
    secret = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
