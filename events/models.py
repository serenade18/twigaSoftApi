import secrets

from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

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
    description = models.TextField(blank=True, help_text='Full details for the event page. Blank lines start new paragraphs.')
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SUMMIT)
    start_date = models.DateField(null=True, blank=True, help_text='Used to sort and to tell upcoming from past events. Leave blank if not confirmed.')
    end_date = models.DateField(null=True, blank=True, help_text='Last day, for events longer than a day.')
    label = models.CharField('button label', max_length=40, default='View Event')
    image = models.CharField('built-in image', max_length=40, choices=Image.choices, default=Image.LEFT,
                             help_text='Used when no cover image is uploaded.')
    cover = models.ImageField(upload_to='events/', blank=True,
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    is_published = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False, help_text='Featured events lead the home page.')
    bookings_open = models.BooleanField(default=True, help_text='Visitors can book seats while the event is upcoming and not full.')
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text='Total seats. Leave blank for no limit.')
    view_count = models.PositiveIntegerField(default=0, editable=False)
    sort_order = models.PositiveIntegerField(default=0, help_text='Lower numbers appear first.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title

    @property
    def last_day(self):
        return self.end_date or self.start_date

    def is_past(self, today=None):
        return self.last_day is not None and self.last_day < (today or timezone.localdate())

    def seats_booked(self):
        """Seats held by bookings that are approved or awaiting approval (pending bookings hold their seats)."""
        return self.bookings.filter(status__in=Booking.HOLDS_SEATS).aggregate(n=Sum('attendees'))['n'] or 0

    def runs_on(self, day):
        """Whether `day` is one of the event's days (tickets can only be checked in then)."""
        return self.start_date is not None and self.start_date <= day <= (self.end_date or self.start_date)

    def seats_left(self, booked=None):
        """Seats still available, or None when the event has no capacity limit."""
        if self.capacity is None:
            return None
        return max(0, self.capacity - (self.seats_booked() if booked is None else booked))

    def booking_closed_reason(self):
        """Why visitors can't book right now, or None when they can."""
        if not self.is_published or not self.bookings_open:
            return 'Bookings are closed for this event.'
        if self.is_past():
            return 'This event has already taken place.'
        if self.seats_left() == 0:
            return 'This event is fully booked.'
        return None

    def save(self, *args, **kwargs):
        if not self.period and self.start_date:
            # Dates can still be strings here when set in code (e.g. Event.objects.create(start_date='2027-03-10')).
            to_date = self._meta.get_field('start_date').to_python
            self.period = format_period(to_date(self.start_date), to_date(self.end_date))
        super().save(*args, **kwargs)


BOOKING_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O or 1/I
MAX_ATTENDEES = 20


def new_token():
    return secrets.token_urlsafe(32)


def new_ticket_code():
    return secrets.token_urlsafe(16)


def new_booking_reference():
    return f'EVB-{timezone.now():%y%m%d}-' + ''.join(secrets.choice(BOOKING_ALPHABET) for _ in range(5))


class Booking(models.Model):
    """A visitor's seat reservation for an event. No payment is taken."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending approval'
        CONFIRMED = 'confirmed', 'Approved'
        CANCELLED = 'cancelled', 'Cancelled'

    HOLDS_SEATS = [Status.PENDING, Status.CONFIRMED]

    reference = models.CharField(max_length=20, unique=True, default=new_booking_reference, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='bookings')
    name = models.CharField(max_length=120)
    email = models.EmailField(max_length=200)
    phone = models.CharField(max_length=40, blank=True)
    organisation = models.CharField(max_length=160, blank=True)
    country = models.CharField(max_length=80)
    attendees = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(MAX_ATTENDEES)])
    message = models.TextField(max_length=1000, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField('internal notes', blank=True)
    # Secret for the booker's tickets page and PDF link (emailed on approval).
    access_token = models.CharField(max_length=43, unique=True, default=new_token, editable=False)
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} · {self.name} ({self.attendees})'


class EventDailyViews(models.Model):
    """Page views of an event per day, for the performance chart. `Event.view_count` keeps the all-time total."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='daily_views')
    date = models.DateField()
    views = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['event', 'date'], name='events_daily_views_unique_day')]
        ordering = ['date']


class Ticket(models.Model):
    """One admission (seat) of an approved booking. Its QR code holds `code`, which checks in once, on an event day."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='tickets')
    number = models.PositiveSmallIntegerField()
    code = models.CharField(max_length=32, unique=True, default=new_ticket_code, editable=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        ordering = ['booking', 'number']
        constraints = [models.UniqueConstraint(fields=['booking', 'number'], name='events_ticket_unique_number')]

    def __str__(self):
        return f'{self.booking.reference} #{self.number}'
