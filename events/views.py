import csv
import logging

from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Booking, Event, new_booking_reference
from .serializers import AdminBookingSerializer, AdminEventSerializer, BookingCreateSerializer, EventDetailSerializer, EventSerializer

logger = logging.getLogger(__name__)
CONFIRMED = Q(bookings__status=Booking.Status.CONFIRMED)


def with_booking_stats(events):
    return events.annotate(
        confirmed_bookings=Count('bookings', filter=CONFIRMED),
        seats_booked_total=Coalesce(Sum('bookings__attendees', filter=CONFIRMED), 0),
    )


def send_booking_confirmation(booking):
    event = booking.event
    seats = f'{booking.attendees} seat' + ('s' if booking.attendees != 1 else '')
    try:
        send_mail(
            subject=f'Booking confirmed: {event.title} ({booking.reference})',
            message=(
                f'Hello {booking.name},\n\n'
                f'Your booking for {event.title} is confirmed.\n\n'
                f'Reference: {booking.reference}\nSeats: {seats}\nWhen: {event.period}\nWhere: {event.location}\n\n'
                'There is nothing to pay now. We will be in touch with participation details before the event.\n'
                'If your plans change, reply to this email with your reference.\n\nAFRIGULF Exchange'
            ),
            from_email=None,
            recipient_list=[booking.email],
        )
    except Exception:
        logger.exception('Could not send booking confirmation %s', booking.reference)


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
        Event.objects.filter(slug=slug, is_published=True).update(view_count=F('view_count') + 1)
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
            return Response({'reference': new_booking_reference(), 'attendees': data['attendees']}, status=status.HTTP_201_CREATED)

        with transaction.atomic():
            # Lock the event so two visitors can't both take the last seats.
            event = get_object_or_404(Event.objects.select_for_update(), slug=slug, is_published=True)
            reason = event.booking_closed_reason()
            if reason:
                raise serializers.ValidationError(reason)
            left = event.seats_left()
            if left is not None and data['attendees'] > left:
                raise serializers.ValidationError({'attendees': [f'Only {left} seat{"s" if left != 1 else ""} left.']})
            if event.bookings.filter(email__iexact=data['email'], status=Booking.Status.CONFIRMED).exists():
                raise serializers.ValidationError({'email': ['This email already has a booking for this event. Check your confirmation email.']})
            booking = serializer.save(event=event, ip_address=request.META.get('REMOTE_ADDR'))
            transaction.on_commit(lambda: send_booking_confirmation(booking))

        return Response({'reference': booking.reference, 'attendees': booking.attendees}, status=status.HTTP_201_CREATED)


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
        bookings = event.bookings.select_related('event')
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
    def patch(self, request, reference):
        booking = get_object_or_404(Booking.objects.select_related('event'), reference=reference)
        serializer = AdminBookingSerializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'booking': serializer.data})
