from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import new_reference
from .serializers import EnquirySerializer


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
