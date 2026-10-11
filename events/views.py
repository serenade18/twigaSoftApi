import csv
from collections import Counter
from datetime import datetime, time, timedelta

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Booking, Event, EventDailyViews, Ticket, new_booking_reference
from .serializers import AdminBookingSerializer, AdminEventSerializer, BookingCreateSerializer, EventDetailSerializer, EventSerializer
from .tickets import (
    QR_PREFIX, CheckInError, check_in, issue_tickets, render_tickets_pdf, send_booking_cancelled, send_booking_received, send_tickets,
)

HOLDS_SEATS = Q(bookings__status__in=Booking.HOLDS_SEATS)


def with_booking_stats(events):
    return events.annotate(
        active_bookings=Count('bookings', filter=HOLDS_SEATS),
        pending_bookings=Count('bookings', filter=Q(bookings__status=Booking.Status.PENDING)),
        seats_booked_total=Coalesce(Sum('bookings__attendees', filter=HOLDS_SEATS), 0),
    )


class EventListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        events = Event.objects.filter(is_published=True)
        return Response({'events': EventSerializer(events, many=True).data})


class EventDetailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        event = get_object_or_404(Event, slug=slug, is_published=True)
        return Response({'event': EventDetailSerializer(event).data})


class EventViewCountView(APIView):
    """Counts a visit to an event's page. The site sends this once per browser session per event."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'event_views'

    def post(self, request, slug):
        event = Event.objects.filter(slug=slug, is_published=True).first()
        if event is not None:
            with transaction.atomic():
                Event.objects.filter(pk=event.pk).update(view_count=F('view_count') + 1)
                day, _ = EventDailyViews.objects.get_or_create(event=event, date=timezone.localdate())
                EventDailyViews.objects.filter(pk=day.pk).update(views=F('views') + 1)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EventBookingView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'bookings'

    def post(self, request, slug):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get('website'):
            # Looks like a bot: answer as if it worked, but don't store anything.
            return Response({'reference': new_booking_reference(), 'attendees': data['attendees'], 'status': Booking.Status.PENDING},
                            status=status.HTTP_201_CREATED)

        with transaction.atomic():
            # Lock the event so two visitors can't both take the last seats.
            event = get_object_or_404(Event.objects.select_for_update(), slug=slug, is_published=True)
            reason = event.booking_closed_reason()
            if reason:
                raise serializers.ValidationError(reason)
            left = event.seats_left()
            if left is not None and data['attendees'] > left:
                raise serializers.ValidationError({'attendees': [f'Only {left} seat{"s" if left != 1 else ""} left.']})
            if event.bookings.filter(email__iexact=data['email'], status__in=Booking.HOLDS_SEATS).exists():
                raise serializers.ValidationError({'email': ['This email already has a booking for this event. Check your confirmation email.']})
            booking = serializer.save(event=event, ip_address=request.META.get('REMOTE_ADDR'))
            transaction.on_commit(lambda: send_booking_received(booking))

        return Response({'reference': booking.reference, 'attendees': booking.attendees, 'status': booking.status}, status=status.HTTP_201_CREATED)


class AdminEventListView(APIView):
    """Every event, drafts included. Filter with `status` (published | draft), `category` and `search`."""

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        events = with_booking_stats(Event.objects.all())
        search = request.query_params.get('search', '').strip()
        if search:
            events = events.filter(Q(title__icontains=search) | Q(location__icontains=search) | Q(organiser__icontains=search))
        category = request.query_params.get('category', '')
        if category in Event.Category.values:
            events = events.filter(category=category)
        # Counts follow the search and category but not the status filter, for the status tabs.
        counts = events.aggregate(published=Count('id', filter=Q(is_published=True)), draft=Count('id', filter=Q(is_published=False)))
        status_filter = request.query_params.get('status', '')
        if status_filter in ('published', 'draft'):
            events = events.filter(is_published=status_filter == 'published')
        return Response({'events': AdminEventSerializer(events, many=True).data, 'statusCounts': counts})

    def post(self, request):
        serializer = AdminEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        return Response({'event': AdminEventSerializer(event).data}, status=status.HTTP_201_CREATED)


class AdminEventDetailView(APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, pk):
        return Response({'event': AdminEventSerializer(get_object_or_404(Event, pk=pk)).data})

    def patch(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        serializer = AdminEventSerializer(event, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response({'event': AdminEventSerializer(serializer.save()).data})

    def delete(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        event.cover.delete(save=False)
        event.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminEventBookingsView(APIView):
    """An event's bookings, newest first. Filter with `status` and `search`; add `?export=csv` for a spreadsheet
    (not `format`, which DRF reserves for content negotiation)."""

    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        bookings = event.bookings.select_related('event').prefetch_related('tickets')
        search = request.query_params.get('search', '').strip()
        if search:
            bookings = bookings.filter(Q(reference__icontains=search) | Q(name__icontains=search) | Q(email__icontains=search)
                                       | Q(organisation__icontains=search) | Q(country__icontains=search))
        counts = dict(bookings.order_by().values_list('status').annotate(n=Count('id')))
        status_filter = request.query_params.get('status', '')
        if status_filter in Booking.Status.values:
            bookings = bookings.filter(status=status_filter)

        if request.query_params.get('export') == 'csv':
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{event.slug}-bookings.csv"'
            writer = csv.writer(response)
            writer.writerow(['Reference', 'Booked at', 'Status', 'Name', 'Email', 'Phone', 'Organisation', 'Country', 'Seats', 'Message', 'Notes'])
            for b in bookings:
                writer.writerow([b.reference, b.created_at.isoformat(timespec='minutes'), b.get_status_display(), b.name, b.email, b.phone,
                                 b.organisation, b.country, b.attendees, b.message, b.notes])
            return response

        return Response({
            'bookings': AdminBookingSerializer(bookings, many=True).data,
            'statusCounts': {value: counts.get(value, 0) for value in Booking.Status.values},
            'event': AdminEventSerializer(event).data,
        })


class AdminBookingDetailView(APIView):
    """Approve (status `confirmed`), decline/cancel (`cancelled`) or annotate a booking. Approval issues and emails the tickets."""

    def patch(self, request, reference):
        with transaction.atomic():
            booking = get_object_or_404(Booking.objects.select_for_update().select_related('event'), reference=reference)
            previous = booking.status
            serializer = AdminBookingSerializer(booking, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            new_status = serializer.validated_data.get('status', previous)
            if new_status == Booking.Status.CONFIRMED and previous != Booking.Status.CONFIRMED:
                if previous == Booking.Status.CANCELLED:
                    # Restoring takes its seats back, so check they're still free.
                    left = booking.event.seats_left()
                    if left is not None and booking.attendees > left:
                        raise serializers.ValidationError(f'Only {left} seat{"s" if left != 1 else ""} left, so this booking can’t be restored.')
                booking = serializer.save(approved_at=timezone.now())
                issue_tickets(booking)
                transaction.on_commit(lambda: send_tickets(booking))
            elif new_status == Booking.Status.CANCELLED and previous != Booking.Status.CANCELLED:
                booking = serializer.save()
                was_approved = previous == Booking.Status.CONFIRMED
                transaction.on_commit(lambda: send_booking_cancelled(booking, was_approved))
            else:
                booking = serializer.save()
        return Response({'booking': AdminBookingSerializer(booking).data})


class AdminResendTicketsView(APIView):
    def post(self, request, reference):
        booking = get_object_or_404(Booking.objects.select_related('event'), reference=reference)
        if booking.status != Booking.Status.CONFIRMED:
            raise serializers.ValidationError('Only approved bookings have tickets to send.')
        send_tickets(booking)
        return Response({'detail': f'Tickets sent to {booking.email}.'})


class TicketsView(APIView):
    """The booker's tickets page (reached from the approval email). The token in the URL is the only credential."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        booking = get_object_or_404(Booking.objects.select_related('event'), access_token=token)
        approved = booking.status == Booking.Status.CONFIRMED
        event = booking.event
        return Response({
            'reference': booking.reference,
            'name': booking.name,
            'status': booking.status,
            'attendees': booking.attendees,
            'event': {'title': event.title, 'slug': event.slug, 'period': event.period, 'location': event.location,
                      'organiser': event.organiser, 'imageUrl': event.cover.url if event.cover else None},
            'tickets': [
                {'number': t.number, 'qr': QR_PREFIX + t.code, 'checkedInAt': t.checked_in_at}
                for t in (issue_tickets(booking) if approved else [])
            ],
        })


class TicketsPdfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        booking = get_object_or_404(Booking.objects.select_related('event'), access_token=token, status=Booking.Status.CONFIRMED)
        response = HttpResponse(render_tickets_pdf(booking), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="tickets-{booking.reference}.pdf"'
        return response


class CheckInView(APIView):
    """Scan a ticket at the door. Staff only; each ticket works once, on an event day."""

    def post(self, request):
        code = str(request.data.get('code', ''))
        if not code.strip():
            raise serializers.ValidationError({'code': ['Scan a QR code or enter a ticket code.']})
        try:
            ticket = check_in(code, request.user)
        except CheckInError as error:
            body = {'error': str(error), 'result': error.result}
            if error.ticket is not None:
                body['ticket'] = _ticket_summary(error.ticket)
            return Response(body, status=status.HTTP_409_CONFLICT if error.result == 'already_used' else status.HTTP_400_BAD_REQUEST)
        return Response({'result': 'admitted', 'ticket': _ticket_summary(ticket)})


def _ticket_summary(ticket):
    booking, event = ticket.booking, ticket.booking.event
    admitted = Ticket.objects.filter(booking__event=event, booking__status=Booking.Status.CONFIRMED, checked_in_at__isnull=False).count()
    issued = Ticket.objects.filter(booking__event=event, booking__status=Booking.Status.CONFIRMED).count()
    return {
        'number': ticket.number,
        'of': booking.attendees,
        'name': booking.name,
        'reference': booking.reference,
        'event': event.title,
        'checkedInAt': ticket.checked_in_at,
        'eventCheckedIn': admitted,
        'eventTickets': issued,
    }

PERFORMANCE_RANGES = {'7': 7, '30': 30, '90': 90}


class AdminEventPerformanceView(APIView):
    """Views and seats booked (pending or approved) per day for one event over the last `days` days (7, 30 or 90; default 30)."""

    def get(self, request, pk):
        event = get_object_or_404(Event, pk=pk)
        days = PERFORMANCE_RANGES.get(request.query_params.get('days', ''), 30)
        today = timezone.localdate()
        first_day = today - timedelta(days=days - 1)

        views = dict(event.daily_views.filter(date__gte=first_day).values_list('date', 'views'))
        seats, bookings = Counter(), Counter()
        active = event.bookings.filter(status__in=Booking.HOLDS_SEATS)
        # Bucket in Python (not TruncDate) so it works without MySQL's time zone tables.
        start = timezone.make_aware(datetime.combine(first_day, time.min))
        for created, attendees in active.filter(created_at__gte=start).values_list('created_at', 'attendees'):
            day = timezone.localdate(created)
            seats[day] += attendees
            bookings[day] += 1

        dates = [first_day + timedelta(days=i) for i in range(days)]
        last_week = today - timedelta(days=6)
        return Response({
            'days': days,
            'daily': [{'date': d.isoformat(), 'views': views.get(d, 0), 'bookings': bookings.get(d, 0), 'seats': seats.get(d, 0)} for d in dates],
            'views': {
                'total': event.view_count,
                'lastWeek': event.daily_views.filter(date__gte=last_week).aggregate(n=Coalesce(Sum('views'), 0))['n'],
            },
            'bookings': {
                'active': active.count(),
                'pending': event.bookings.filter(status=Booking.Status.PENDING).count(),
                'cancelled': event.bookings.filter(status=Booking.Status.CANCELLED).count(),
                'seats': event.seats_booked(),
            },
        })


class AdminBookingListView(APIView):
    """Bookings across all events, newest first, 25 per page. Filter with `event` (id), `status` and `search`."""

    page_size = 25

    def get(self, request):
        bookings = Booking.objects.select_related('event').prefetch_related('tickets')
        event_id = request.query_params.get('event', '')
        if event_id.isdigit():
            bookings = bookings.filter(event_id=event_id)
        search = request.query_params.get('search', '').strip()
        if search:
            bookings = bookings.filter(Q(reference__icontains=search) | Q(name__icontains=search) | Q(email__icontains=search)
                                       | Q(organisation__icontains=search) | Q(event__title__icontains=search))
        counts = dict(bookings.order_by().values_list('status').annotate(n=Count('id')))
        status_filter = request.query_params.get('status', '')
        if status_filter in Booking.Status.values:
            bookings = bookings.filter(status=status_filter)
        page = Paginator(bookings, self.page_size).get_page(request.query_params.get('page'))
        return Response({
            'bookings': AdminBookingSerializer(page.object_list, many=True).data,
            'count': page.paginator.count,
            'page': page.number,
            'pages': page.paginator.num_pages,
            'statusCounts': {value: counts.get(value, 0) for value in Booking.Status.values},
            'events': [{'id': str(e.pk), 'title': e.title} for e in Event.objects.filter(bookings__isnull=False).distinct().order_by('title')],
        })
