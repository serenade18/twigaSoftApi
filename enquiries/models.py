import secrets

from django.db import models
from django.utils import timezone

REFERENCE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O or 1/I


def new_reference():
    return f'AGX-{timezone.now():%y%m%d}-' + ''.join(secrets.choice(REFERENCE_ALPHABET) for _ in range(5))


class Enquiry(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'New'
        IN_PROGRESS = 'in_progress', 'In progress'
        CLOSED = 'closed', 'Closed'

    reference = models.CharField(max_length=20, unique=True, default=new_reference, editable=False)
    name = models.CharField(max_length=120)
    email = models.EmailField(max_length=200)
    phone = models.CharField(max_length=40, blank=True)
    country = models.CharField(max_length=80)
    interest = models.CharField(max_length=120)
    message = models.TextField(max_length=2000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    notes = models.TextField('internal notes', blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'enquiries'

    def __str__(self):
        return f'{self.reference} · {self.name}'
