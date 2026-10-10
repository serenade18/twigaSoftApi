"""Password reset tokens. The emailed token is "<uidb64>.<django token>", so the frontend only handles one value."""

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode


def make_reset_token(user):
    return f'{urlsafe_base64_encode(force_bytes(user.pk))}.{default_token_generator.make_token(user)}'


def user_for_reset_token(token):
    """Return the admin the token belongs to, or None if it is malformed, expired or already used."""
    uidb64, _, django_token = token.partition('.')
    try:
        user = get_user_model().objects.get(pk=force_str(urlsafe_base64_decode(uidb64)), is_active=True, is_staff=True)
    except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
        return None
    # Django's tokens are tied to the password hash and last login, so they stop working once used.
    return user if default_token_generator.check_token(user, django_token) else None
