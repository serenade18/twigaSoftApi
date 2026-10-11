from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .passwords import user_for_reset_token

INVALID_LOGIN = 'Incorrect email or password.'


def role_of(user):
    """Admins (superusers) manage staff; staff can use the rest of the admin portal."""
    return 'admin' if user.is_superuser else 'staff'


class AdminSerializer(serializers.Serializer):
    id = serializers.SerializerMethodField()
    email = serializers.EmailField()
    name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    def get_id(self, user):
        return str(user.pk)

    def get_name(self, user):
        return user.get_full_name() or user.email

    def get_role(self, user):
        return role_of(user)


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


class StaffSerializer(serializers.ModelSerializer):
    """A portal account as admins manage it. `password` is write-only: required on create, optional on update."""

    id = serializers.CharField(read_only=True)
    firstName = serializers.CharField(source='first_name', max_length=150, required=False, allow_blank=True)
    lastName = serializers.CharField(source='last_name', max_length=150, required=False, allow_blank=True)
    name = serializers.SerializerMethodField()
    role = serializers.ChoiceField(choices=['admin', 'staff'], default='staff', write_only=True)  # read back via role_of()
    isActive = serializers.BooleanField(source='is_active', required=False)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128, required=False)
    lastLogin = serializers.DateTimeField(source='last_login', read_only=True)
    dateJoined = serializers.DateTimeField(source='date_joined', read_only=True)

    class Meta:
        model = get_user_model()
        fields = ['id', 'email', 'firstName', 'lastName', 'name', 'role', 'isActive', 'password', 'lastLogin', 'dateJoined']
        extra_kwargs = {'email': {'validators': []}}  # uniqueness is checked below, ignoring case

    def get_name(self, user):
        return user.get_full_name() or user.email

    def to_representation(self, user):
        data = super().to_representation(user)
        data['role'] = role_of(user)
        return data

    def validate_email(self, value):
        email = get_user_model().objects.normalize_email(value)
        others = get_user_model().objects.filter(email__iexact=email)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return email

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': ['Set a password for the new account.']})
        if attrs.get('password'):
            user = self.instance or get_user_model()(email=attrs.get('email', ''), first_name=attrs.get('first_name', ''),
                                                       last_name=attrs.get('last_name', ''))
            try:
                validate_password(attrs['password'], user)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'password': list(exc.messages)})
        actor = self.context['request'].user
        if self.instance is not None and self.instance.pk == actor.pk:
            if 'role' in self.initial_data and attrs.get('role') != 'admin':
                raise serializers.ValidationError({'role': ['You can’t remove your own admin access.']})
            if attrs.get('is_active') is False:
                raise serializers.ValidationError({'isActive': ['You can’t deactivate your own account.']})
        return attrs

    def create(self, validated_data):
        role = validated_data.pop('role', 'staff')
        password = validated_data.pop('password')
        return get_user_model().objects.create_user(
            password=password, is_staff=True, is_superuser=role == 'admin', **validated_data,
        )

    def update(self, user, validated_data):
        if 'role' in self.initial_data:
            user.is_superuser = validated_data.pop('role') == 'admin'
        else:
            validated_data.pop('role', None)  # the field's default, not something the admin sent
        password = validated_data.pop('password', None)
        if password:
            user.set_password(password)
        for field, value in validated_data.items():
            setattr(user, field, value)
        user.save()
        return user
