from django.db import models


class UserProfile(models.Model):
    username = models.CharField(max_length=100)
    email = models.EmailField()


class Payment(models.Model):
    amount = models.IntegerField()
    currency = models.CharField(max_length=3, default="USD")


class Order(models.Model):
    reference = models.CharField(max_length=50)
