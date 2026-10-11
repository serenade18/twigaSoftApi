from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Event
from .serializers import AdminEventSerializer, EventSerializer


class EventListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        events = Event.objects.filter(is_published=True)
        return Response({'events': EventSerializer(events, many=True).data})


class AdminEventListView(APIView):
    """Every event, drafts included. Filter with `status` (published | draft), `category` and `search`."""

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        events = Event.objects.all()
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
