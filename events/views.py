from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Event
from .serializers import EventSerializer


class EventListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        events = Event.objects.filter(is_published=True)
        return Response({'events': EventSerializer(events, many=True).data})
