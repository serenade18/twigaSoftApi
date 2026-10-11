from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Enquiry, new_reference
from .serializers import AdminEnquirySerializer, EnquirySerializer


class EnquiryCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'enquiries'

    def post(self, request):
        serializer = EnquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get('website'):
            # Looks like a bot: answer as if it worked, but don't store anything.
            return Response({'reference': new_reference()}, status=status.HTTP_201_CREATED)
        enquiry = serializer.save(ip_address=request.META.get('REMOTE_ADDR'))
        return Response({'reference': enquiry.reference}, status=status.HTTP_201_CREATED)


class AdminEnquiryListView(APIView):
    """Admins' enquiry inbox: newest first, filterable by `status`, searchable with `search`, paged with `page`."""

    page_size = 20

    def get(self, request):
        enquiries = Enquiry.objects.all()
        search = request.query_params.get('search', '').strip()
        if search:
            enquiries = enquiries.filter(
                Q(reference__icontains=search) | Q(name__icontains=search) | Q(email__icontains=search)
                | Q(country__icontains=search) | Q(interest__icontains=search) | Q(message__icontains=search)
            )
        # Counts per status (after search, before the status filter) for the inbox's filter tabs.
        counts = {row['status']: row['n'] for row in enquiries.order_by().values('status').annotate(n=Count('id'))}
        status_filter = request.query_params.get('status', '')
        if status_filter in Enquiry.Status.values:
            enquiries = enquiries.filter(status=status_filter)
        page = Paginator(enquiries, self.page_size).get_page(request.query_params.get('page'))
        return Response({
            'enquiries': AdminEnquirySerializer(page.object_list, many=True).data,
            'count': page.paginator.count,
            'page': page.number,
            'pages': page.paginator.num_pages,
            'statusCounts': {value: counts.get(value, 0) for value in Enquiry.Status.values},
        })


class AdminEnquiryDetailView(APIView):
    def get(self, request, reference):
        enquiry = get_object_or_404(Enquiry, reference=reference)
        return Response({'enquiry': AdminEnquirySerializer(enquiry).data})

    def patch(self, request, reference):
        enquiry = get_object_or_404(Enquiry, reference=reference)
        serializer = AdminEnquirySerializer(enquiry, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'enquiry': serializer.data})
