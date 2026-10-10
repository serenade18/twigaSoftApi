from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .passwords import user_for_reset_token

INVALID_LOGIN = 'Incorrect email or password.'


class AdminSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    email = serializers.EmailField()
    name = serializers.SerializerMethodField()

    def get_id(self, user):
        return str(user.pk)

    def get_name(self, user):
        return user.get_full_name() or user.email


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False, max_length=128)

    def validate(self, attrs):
        User = get_user_model()
        user = User.objects.filter(email__iexact=attrs['email'], is_active=True, is_staff=True).first()
        if user is None:
            User().set_password(attrs['password'])  # hash anyway so unknown emails take as long as wrong passwords
            raise serializers.ValidationError(INVALID_LOGIN)
        if not user.check_password(attrs['password']):
            raise serializers.ValidationError(INVALID_LOGIN)
        attrs['user'] = user
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=300)
    password = serializers.CharField(trim_whitespace=False, max_length=128)

    def validate(self, attrs):
        user = user_for_reset_token(attrs['token'])
        if user is None:
            raise serializers.ValidationError('This reset link is invalid or has expired.')
        try:
            validate_password(attrs['password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        if user.check_password(attrs['password']):
            raise serializers.ValidationError({'password': ['Choose a password you have not used before.']})
        attrs['user'] = user
        return attrs
