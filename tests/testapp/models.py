from django.db import models


class Invoice(models.Model):
    """Backs the field-removal idiom examples (ticket 14). A real model is
    needed because the ModelSerializer footgun — and the Meta.fields
    surgery that fixes it — doesn't exist for a plain Serializer. Never
    migrated or queried; every test builds an unsaved instance directly."""

    number = models.CharField(max_length=32, primary_key=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    internal_note = models.CharField(max_length=200)
