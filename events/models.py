from django.db import models


class Event(models.Model):
    class Image(models.TextChoices):
        # CSS classes the site's event cards use for the card image.
        SUMMIT = 'afrigulf-summit-image', 'AFRIGULF summit artwork'
        LEFT = 'image-one', 'Shared event photo (left)'
        CENTRE = 'image-two', 'Shared event photo (centre)'
        RIGHT = 'image-three', 'Shared event photo (right)'

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=120)
    period = models.CharField(max_length=80, help_text='Shown as written, e.g. "December 2026".')
    organiser = models.CharField(max_length=200)
    summary = models.CharField(max_length=300)
    label = models.CharField('button label', max_length=40, default='View Event')
    image = models.CharField(max_length=40, choices=Image.choices, default=Image.LEFT)
    is_published = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title
