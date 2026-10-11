from rest_framework import serializers

from .models import Enquiry


class EnquirySerializer(serializers.ModelSerializer):
    # Honeypot the site's form keeps hidden; people leave it empty, bots tend to fill it.
    website = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=200)

    class Meta:
        model = Enquiry
        fields = ['name', 'email', 'phone', 'country', 'interest', 'message', 'website']
        extra_kwargs = {
            'name': {'error_messages': {'blank': 'Please enter your full name.'}},
            'email': {'error_messages': {'invalid': 'Please enter a valid email address.'}},
            'country': {'error_messages': {'blank': 'Please enter your country.'}},
            'interest': {'error_messages': {'blank': 'Please choose an area of interest.'}},
        }

    def create(self, validated_data):
        validated_data.pop('website', None)
        return super().create(validated_data)


class AdminEnquirySerializer(serializers.ModelSerializer):
    """Enquiry as admins see it; only status and internal notes can be changed."""

    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = Enquiry
        fields = ['reference', 'name', 'email', 'phone', 'country', 'interest', 'message', 'status', 'notes', 'createdAt']
        read_only_fields = ['reference', 'name', 'email', 'phone', 'country', 'interest', 'message']
