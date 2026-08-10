from django.db import models


class UserProfile(models.Model):
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField()
    full_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
