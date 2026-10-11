from django.utils.text import slugify
from rest_framework import serializers

from .models import Event, format_period

MAX_COVER_BYTES = 5 * 1024 * 1024


def cover_url(event, request=None):
    if not event.cover:
        return None
    return request.build_absolute_uri(event.cover.url) if request else event.cover.url


class EventSerializer(serializers.ModelSerializer):
    """An event as the public site shows it."""

    startDate = serializers.DateField(source='start_date')
    endDate = serializers.DateField(source='end_date')
    imageUrl = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ['slug', 'title', 'location', 'period', 'organiser', 'summary', 'label', 'image', 'imageUrl', 'category', 'startDate', 'endDate']

    def get_imageUrl(self, event):
        return cover_url(event)


class AdminEventSerializer(serializers.ModelSerializer):
    """An event as staff manage it. Accepts JSON or multipart (for `cover`); send `removeCover: true` to drop the cover."""

    id = serializers.CharField(read_only=True)
    slug = serializers.SlugField(max_length=50, required=False, allow_blank=True)
    startDate = serializers.DateField(source='start_date', required=False, allow_null=True)
    endDate = serializers.DateField(source='end_date', required=False, allow_null=True)
    period = serializers.CharField(max_length=80, required=False, allow_blank=True)
    label = serializers.CharField(max_length=40, required=False, allow_blank=True)
    isPublished = serializers.BooleanField(source='is_published', required=False)
    sortOrder = serializers.IntegerField(source='sort_order', required=False, min_value=0)
    cover = serializers.ImageField(required=False, write_only=True)
    removeCover = serializers.BooleanField(required=False, write_only=True, default=False)
    imageUrl = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Event
        fields = [
            'id', 'slug', 'title', 'category', 'location', 'startDate', 'endDate', 'period', 'organiser', 'summary', 'label',
            'image', 'cover', 'removeCover', 'imageUrl', 'isPublished', 'sortOrder', 'createdAt', 'updatedAt',
        ]
        extra_kwargs = {
            'title': {'error_messages': {'blank': 'Please enter a title.'}},
            'location': {'error_messages': {'blank': 'Please enter a location.'}},
            'organiser': {'error_messages': {'blank': 'Please enter the organiser.'}},
            'summary': {'error_messages': {'blank': 'Please add a short summary.'}},
        }

    def get_imageUrl(self, event):
        return cover_url(event)

    def to_internal_value(self, data):
        attrs = super().to_internal_value(data)
        # DRF reads a boolean missing from multipart data as False; treat "not sent" as "unchanged" (or the default).
        if 'isPublished' not in data:
            attrs.pop('is_published', None)
        return attrs

    def validate_cover(self, cover):
        if cover.size > MAX_COVER_BYTES:
            raise serializers.ValidationError('Use an image under 5 MB.')
        if cover.name.rsplit('.', 1)[-1].lower() not in {'jpg', 'jpeg', 'png', 'webp'}:
            raise serializers.ValidationError('Use a JPG, PNG or WebP image.')
        return cover

    def validate_slug(self, slug):
        others = Event.objects.filter(slug=slug)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if slug and others.exists():
            raise serializers.ValidationError('Another event already uses this web address.')
        return slug

    def validate(self, attrs):
        get = lambda field: attrs.get(field, getattr(self.instance, field, None))  # noqa: E731
        start, end = get('start_date'), get('end_date')
        if end and not start:
            raise serializers.ValidationError({'startDate': ['Add a start date as well as an end date.']})
        if start and end and end < start:
            raise serializers.ValidationError({'endDate': ['The end date can’t be before the start date.']})
        attrs['period'] = self._period(attrs, start, end)
        return attrs

    def _period(self, attrs, start, end):
        """Keep a period the editor typed; otherwise (or when the dates of a generated one change) build it from the dates."""
        event = self.instance
        if 'period' in attrs:
            period = attrs['period'].strip()
        elif event is None:
            period = ''
        elif {'start_date', 'end_date'} & attrs.keys() and event.start_date and event.period == format_period(event.start_date, event.end_date):
            period = ''
        else:
            period = event.period
        if period:
            return period
        if not start:
            raise serializers.ValidationError({'period': ['Add a start date, or describe when it happens (e.g. “December 2026”).']})
        return format_period(start, end)

    def create(self, validated_data):
        validated_data.pop('removeCover', None)
        validated_data['label'] = validated_data.get('label') or 'View Event'
        validated_data['slug'] = validated_data.get('slug') or self._unique_slug(validated_data['title'])
        return super().create(validated_data)

    def update(self, event, validated_data):
        if validated_data.pop('removeCover', False) and 'cover' not in validated_data:
            event.cover.delete(save=False)
            event.cover = None
        elif 'cover' in validated_data and event.cover:
            event.cover.delete(save=False)  # replaced: don't leave the old file behind
        if 'slug' in validated_data and not validated_data['slug']:
            validated_data['slug'] = self._unique_slug(validated_data.get('title', event.title), exclude=event.pk)
        if 'label' in validated_data and not validated_data['label']:
            validated_data['label'] = 'View Event'
        return super().update(event, validated_data)

    @staticmethod
    def _unique_slug(title, exclude=None):
        base = slugify(title)[:44] or 'event'
        slug, n = base, 2
        while Event.objects.filter(slug=slug).exclude(pk=exclude).exists():
            slug, n = f'{base}-{n}', n + 1
        return slug
