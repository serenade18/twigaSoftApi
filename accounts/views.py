import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.core.mail import send_mail
from django.db import transaction
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .passwords import make_reset_token
from .serializers import AdminSerializer, ForgotPasswordSerializer, LoginSerializer, ResetPasswordSerializer, StaffSerializer

logger = logging.getLogger(__name__)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'admin_login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        # One active token per admin; signing in again replaces it and restarts the expiry clock.
        with transaction.atomic():
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)
        update_last_login(None, user)
        return Response({'token': token.key, 'admin': AdminSerializer(user).data})


class LogoutView(APIView):
    def post(self, request):
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response({'admin': AdminSerializer(request.user).data})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset'

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = get_user_model().objects.filter(email__iexact=email, is_active=True, is_staff=True).first()
        if user is not None:
            link = f'{settings.FRONTEND_URL}/admin/reset-password?token={make_reset_token(user)}'
            minutes = settings.PASSWORD_RESET_TIMEOUT // 60
            try:
                send_mail(
                    subject='Reset your AFRIGULF Exchange admin password',
                    message=(
                        f'Hello {user.get_full_name() or user.email},\n\n'
                        f'Use this link to choose a new password. It expires in {minutes} minutes and works once:\n\n'
                        f'{link}\n\nIf you did not ask for this, you can ignore this email.'
                    ),
                    from_email=None,
                    recipient_list=[user.email],
                )
            except Exception:
                logger.exception('Could not send password reset email to admin %s', user.pk)
        # Same response whether or not the account exists, so emails can't be probed.
        return Response({'detail': 'If an admin account exists for that email, a reset link has been sent.'})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'password_reset_confirm'

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        user.set_password(serializer.validated_data['password'])
        user.save(update_fields=['password'])
        Token.objects.filter(user=user).delete()  # sign out everywhere
        return Response({'detail': 'Your password has been updated.'})


class IsPortalAdmin(BasePermission):
    """Only admins (superusers) may manage staff accounts."""

    message = 'Only admins can manage staff.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_active and request.user.is_staff and request.user.is_superuser)


class StaffListView(APIView):
    permission_classes = [IsPortalAdmin]

    def get(self, request):
        members = get_user_model().objects.filter(is_staff=True).order_by('-is_active', '-is_superuser', 'first_name', 'email')
        return Response({'staff': StaffSerializer(members, many=True).data})

    def post(self, request):
        serializer = StaffSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        member = serializer.save()
        return Response({'member': StaffSerializer(member).data}, status=status.HTTP_201_CREATED)


class StaffDetailView(APIView):
    permission_classes = [IsPortalAdmin]

    def patch(self, request, pk):
        member = get_object_or_404(get_user_model(), pk=pk, is_staff=True)
        serializer = StaffSerializer(member, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        member = serializer.save()
        # A deactivated account or a new password ends that person's current session.
        if not member.is_active or serializer.validated_data.get('password'):
            Token.objects.filter(user=member).delete()
        return Response({'member': StaffSerializer(member).data})
