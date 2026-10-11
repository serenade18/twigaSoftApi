from collections import Counter
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from enquiries.models import Enquiry
from enquiries.serializers import AdminEnquirySerializer
from events.models import Event

RANGES = {'7': 7, '30': 30, '90': 90}
TOP_N = 6


def _top(queryset, field):
    rows = queryset.order_by().values(field).annotate(n=Count('id')).order_by('-n', field)
    return [{'label': row[field], 'count': row['n']} for row in rows[:TOP_N]]


class StatsView(APIView):
    """Dashboard figures. `days` (7, 30 or 90; default 30) scopes everything except the all-time totals."""

    def get(self, request):
        days = RANGES.get(request.query_params.get('days', ''), 30)
        today = timezone.localdate()
        first_day = today - timedelta(days=days - 1)
        start = timezone.make_aware(datetime.combine(first_day, time.min))
        previous_start = start - timedelta(days=days)

        in_range = Enquiry.objects.filter(created_at__gte=start)
        # Bucket in Python rather than with TruncDate, so it works without MySQL's time zone tables.
        per_day = Counter(timezone.localdate(created) for created in in_range.values_list('created_at', flat=True))
        by_status = dict(in_range.order_by().values_list('status').annotate(n=Count('id')))

        return Response({
            'days': days,
            'totals': {
                'enquiries': Enquiry.objects.count(),
                'awaitingReply': Enquiry.objects.filter(status=Enquiry.Status.NEW).count(),
                'publishedEvents': Event.objects.filter(is_published=True).count(),
                'activeStaff': get_user_model().objects.filter(is_staff=True, is_active=True).count(),
            },
            'period': {
                'enquiries': sum(per_day.values()),
                'previous': Enquiry.objects.filter(created_at__gte=previous_start, created_at__lt=start).count(),
            },
            'daily': [
                {'date': day.isoformat(), 'count': per_day.get(day, 0)}
                for day in (first_day + timedelta(days=i) for i in range(days))
            ],
            'byStatus': {value: by_status.get(value, 0) for value in Enquiry.Status.values},
            'topInterests': _top(in_range, 'interest'),
            'topCountries': _top(in_range, 'country'),
            'recent': AdminEnquirySerializer(Enquiry.objects.all()[:5], many=True).data,
        })
