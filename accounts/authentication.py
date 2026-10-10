from django.conf import settings
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import TokenAuthentication


class ExpiringTokenAuthentication(TokenAuthentication):
    """DRF token auth (`Authorization: Bearer <token>`) where tokens expire ADMIN_TOKEN_TTL after sign-in."""

    keyword = 'Bearer'

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if timezone.now() - token.created > settings.ADMIN_TOKEN_TTL:
            token.delete()
            raise exceptions.AuthenticationFailed('Your session has expired. Please sign in again.')
        return user, token
