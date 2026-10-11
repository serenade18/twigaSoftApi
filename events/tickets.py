"""Tickets for approved bookings: issuing them, the PDF, the emails, and checking them in at the door."""

import io
import logging
from zoneinfo import ZoneInfo

import qrcode
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .models import Booking, Ticket

logger = logging.getLogger(__name__)

# What the QR code holds: a prefix (so the scanner can reject other QR codes) and the ticket's secret code.
QR_PREFIX = 'AGXT1:'
NAVY, GOLD, INK, MUTED = HexColor('#0d2b45'), HexColor('#c99342'), HexColor('#0a1956'), HexColor('#52667a')


def tickets_url(booking):
    return f'{settings.FRONTEND_URL}/tickets/{booking.access_token}'


def event_today():
    """Today in the events' time zone, which decides whether a ticket can be checked in."""
    return timezone.localdate(timezone=ZoneInfo(settings.EVENT_TIME_ZONE))


def issue_tickets(booking):
    """Create one ticket per seat (idempotent: existing tickets keep their codes)."""
    existing = set(booking.tickets.values_list('number', flat=True))
    Ticket.objects.bulk_create(Ticket(booking=booking, number=n) for n in range(1, booking.attendees + 1) if n not in existing)
    return list(booking.tickets.all())


def _qr_image(code):
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=1, box_size=10)
    qr.add_data(QR_PREFIX + code)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color='#0a1956', back_color='white').save(buffer, 'PNG')
    buffer.seek(0)
    return ImageReader(buffer)


def render_tickets_pdf(booking):
    """One A5-landscape page per ticket, each with its own QR code."""
    event = booking.event
    tickets = issue_tickets(booking)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A5))
    pdf.setTitle(f'Tickets {booking.reference} - {event.title}')
    pdf.setAuthor('AFRIGULF Exchange')
    width, height = landscape(A5)
    for ticket in tickets:
        # Header band
        pdf.setFillColor(NAVY)
        pdf.rect(0, height - 70, width, 70, stroke=0, fill=1)
        pdf.setFillColor(GOLD)
        pdf.setFont('Helvetica-Bold', 10)
        pdf.drawString(32, height - 32, 'AFRIGULF EXCHANGE · EVENT TICKET')
        pdf.setFillColor(white)
        pdf.setFont('Helvetica', 10)
        pdf.drawRightString(width - 32, height - 32, f'Ticket {ticket.number} of {len(tickets)}')
        pdf.setFillColor(GOLD)
        pdf.rect(0, height - 74, width, 4, stroke=0, fill=1)

        # Details (left)
        y = height - 115
        pdf.setFillColor(INK)
        pdf.setFont('Helvetica-Bold', 20)
        for line in _wrap(event.title, 'Helvetica-Bold', 20, width - 300):
            pdf.drawString(32, y, line)
            y -= 24
        y -= 8
        for label, value in [('When', event.period), ('Where', event.location), ('Name', booking.name), ('Booking', booking.reference)]:
            pdf.setFillColor(MUTED)
            pdf.setFont('Helvetica', 9)
            pdf.drawString(32, y, label.upper())
            pdf.setFillColor(INK)
            pdf.setFont('Helvetica-Bold', 13)
            pdf.drawString(32, y - 16, value[:48])
            y -= 40

        # QR (right)
        size = 190
        qr_x, qr_y = width - size - 40, height - 100 - size
        pdf.drawImage(_qr_image(ticket.code), qr_x, qr_y, size, size)
        pdf.setFillColor(MUTED)
        pdf.setFont('Helvetica', 8)
        pdf.drawCentredString(qr_x + size / 2, qr_y - 14, ticket.code)  # for typing in if the QR won't scan

        # Footer
        pdf.setFillColor(MUTED)
        pdf.setFont('Helvetica', 8.5)
        pdf.drawString(32, 30, 'Valid for one entry, on the day of the event. Each QR code can be scanned only once — do not share it.')
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _wrap(text, font, size, max_width):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    lines, current = [], ''
    for word in text.split():
        candidate = f'{current} {word}'.strip()
        if stringWidth(candidate, font, size) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    return (lines + [current])[:3]


def _send(booking, subject, body, attachment=None):
    message = EmailMessage(subject=subject, body=body, to=[booking.email])
    if attachment:
        message.attach(*attachment)
    try:
        message.send()
    except Exception:
        logger.exception('Could not send "%s" email for booking %s', subject, booking.reference)


def _seats(booking):
    return f'{booking.attendees} seat' + ('s' if booking.attendees != 1 else '')


def send_booking_received(booking):
    event = booking.event
    _send(booking, f'Booking request received: {event.title} ({booking.reference})', (
        f'Hello {booking.name},\n\nThanks for booking {_seats(booking)} for {event.title}.\n\n'
        f'Reference: {booking.reference}\nWhen: {event.period}\nWhere: {event.location}\n\n'
        'Our team will review your request. Once it is approved we will email your tickets.\n'
        'There is nothing to pay.\n\nAFRIGULF Exchange'
    ))


def send_tickets(booking):
    event = booking.event
    _send(booking, f'Your tickets: {event.title} ({booking.reference})', (
        f'Hello {booking.name},\n\nGood news: your booking for {event.title} is approved.\n\n'
        f'Reference: {booking.reference}\nSeats: {booking.attendees}\nWhen: {event.period}\nWhere: {event.location}\n\n'
        f'Your tickets are attached as a PDF. You can also view and download them here:\n{tickets_url(booking)}\n\n'
        'Each ticket has a QR code that is scanned at the entrance. It works once, on the day of the event, '
        'so please don\'t share it.\n\nAFRIGULF Exchange'
    ), attachment=(f'tickets-{booking.reference}.pdf', render_tickets_pdf(booking), 'application/pdf'))


def send_booking_cancelled(booking, was_approved):
    event = booking.event
    detail = 'Your tickets are no longer valid.' if was_approved else 'We were unable to approve your booking request.'
    _send(booking, f'Booking cancelled: {event.title} ({booking.reference})', (
        f'Hello {booking.name},\n\nYour booking {booking.reference} for {event.title} has been cancelled. {detail}\n\n'
        'If you think this is a mistake, reply to this email.\n\nAFRIGULF Exchange'
    ))


class CheckInError(Exception):
    def __init__(self, message, result, ticket=None):
        super().__init__(message)
        self.result, self.ticket = result, ticket


def check_in(raw_code, user):
    """Admit a ticket: it must exist, belong to an approved booking, be used on an event day, and not be used before."""
    code = raw_code.strip().removeprefix(QR_PREFIX)
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().select_related('booking__event').filter(code=code).first()
        if ticket is None:
            raise CheckInError('This QR code isn’t a valid ticket.', 'invalid')
        booking, event = ticket.booking, ticket.booking.event
        if booking.status != Booking.Status.CONFIRMED:
            raise CheckInError('This booking has been cancelled, so the ticket isn’t valid.', 'cancelled', ticket)
        today = event_today()
        if not event.runs_on(today):
            when = event.period or 'another day'
            raise CheckInError(f'This ticket is for {event.title} ({when}). It can only be scanned on the day of the event.', 'wrong_day', ticket)
        if ticket.checked_in_at is not None:
            raise CheckInError('This ticket has already been used.', 'already_used', ticket)
        ticket.checked_in_at = timezone.now()
        ticket.checked_in_by = user
        ticket.save(update_fields=['checked_in_at', 'checked_in_by'])
    return ticket
