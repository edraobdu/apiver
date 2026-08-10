from django.db import models


class Order(models.Model):
    reference = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default="open")
