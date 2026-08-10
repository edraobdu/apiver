from django.db import models

from users.models import UserProfile


class Notification(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="notifications")
    verb = models.CharField(max_length=100)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
