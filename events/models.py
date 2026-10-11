from django.core.validators import FileExtensionValidator
from django.db import models

MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


def format_period(start, end=None):
    """Display text for an event's dates, e.g. "10 March 2027", "10–11 March 2027", "28 February – 2 March 2027"."""
    if end is None or end == start:
        return f'{start.day} {MONTHS[start.month - 1]} {start.year}'
    if (start.year, start.month) == (end.year, end.month):
        return f'{start.day}–{end.day} {MONTHS[end.month - 1]} {end.year}'
    if start.year == end.year:
        return f'{start.day} {MONTHS[start.month - 1]} – {end.day} {MONTHS[end.month - 1]} {end.year}'
    return f'{format_period(start)} – {format_period(end)}'


class Event(models.Model):
    class Category(models.TextChoices):
        SUMMIT = 'summit', 'Summit'
        CONFERENCE = 'conference', 'Conference'
        EXHIBITION = 'exhibition', 'Exhibition'
        TRADE_MISSION = 'trade_mission', 'Trade mission'
        WORKSHOP = 'workshop', 'Workshop'
        NETWORKING = 'networking', 'Networking'

    class Image(models.TextChoices):
        # CSS classes the site's event cards use for the card image.
        SUMMIT = 'afrigulf-summit-image', 'AFRIGULF summit artwork'
        LEFT = 'image-one', 'Shared event photo (left)'
        CENTRE = 'image-two', 'Shared event photo (centre)'
        RIGHT = 'image-three', 'Shared event photo (right)'

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    location = models.CharField(max_length=120)
    period = models.CharField(max_length=80, blank=True,
                              help_text='Shown as written, e.g. "December 2026". Left blank, it is generated from the dates.')
    organiser = models.CharField(max_length=200)
    summary = models.CharField(max_length=300)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SUMMIT)
    start_date = models.DateField(null=True, blank=True, help_text='Used to sort and to tell upcoming from past events. Leave blank if not confirmed.')
    end_date = models.DateField(null=True, blank=True, help_text='Last day, for events longer than a day.')
    label = models.CharField('button label', max_length=40, default='View Event')
    image = models.CharField('built-in image', max_length=40, choices=Image.choices, default=Image.LEFT,
                             help_text='Used when no cover image is uploaded.')
    cover = models.ImageField(upload_to='events/', blank=True,
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    is_published = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.period and self.start_date:
            self.period = format_period(self.start_date, self.end_date)
        super().save(*args, **kwargs)
