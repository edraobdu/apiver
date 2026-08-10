from django.db import models


class LegacyInvoice(models.Model):
    number = models.CharField(max_length=50)
    amount = models.IntegerField()
