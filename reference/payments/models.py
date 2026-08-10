from django.db import models


class Payment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    amount = models.IntegerField(help_text="Amount in cents")
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    # flat card fields — a real project would probably nest these under "card" today;
    # this one didn't, and nobody's gotten around to it
    card_last4 = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
