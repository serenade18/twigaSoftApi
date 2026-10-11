import secrets

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import events.models


def give_existing_bookings_tokens(apps, schema_editor):
    """Existing bookings were confirmed without approval; give each its own tickets-page token."""
    Booking = apps.get_model('events', 'Booking')
    for booking in Booking.objects.filter(access_token__isnull=True):
        booking.access_token = secrets.token_urlsafe(32)
        booking.save(update_fields=['access_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0006_featured_and_daily_views'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending approval'), ('confirmed', 'Approved'), ('cancelled', 'Cancelled')],
                                   default='pending', max_length=20),
        ),
        migrations.AddField(model_name='booking', name='approved_at', field=models.DateTimeField(blank=True, editable=False, null=True)),
        # Unique token: add it empty, fill it per row, then make it required and unique.
        migrations.AddField(model_name='booking', name='access_token', field=models.CharField(editable=False, max_length=43, null=True)),
        migrations.RunPython(give_existing_bookings_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='booking',
            name='access_token',
            field=models.CharField(default=events.models.new_token, editable=False, max_length=43, unique=True),
        ),
        migrations.CreateModel(
            name='Ticket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveSmallIntegerField()),
                ('code', models.CharField(default=events.models.new_ticket_code, editable=False, max_length=32, unique=True)),
                ('checked_in_at', models.DateTimeField(blank=True, null=True)),
                ('booking', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tickets', to='events.booking')),
                ('checked_in_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                                                    to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['booking', 'number']},
        ),
        migrations.AddConstraint(
            model_name='ticket',
            constraint=models.UniqueConstraint(fields=('booking', 'number'), name='events_ticket_unique_number'),
        ),
    ]
