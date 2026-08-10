from django.db import models

from users.models import UserProfile

# The project's first relational field — every other app so far stands alone.
# A real V2 override touching a nested/related resource has to cope with this,
# not just with flat models.
COUNTRY_CHOICES = [
    ("US", "United States"),
    ("CA", "Canada"),
    ("MX", "Mexico"),
]


class Address(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="addresses")
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=2, choices=COUNTRY_CHOICES)
    is_primary = models.BooleanField(default=False)
