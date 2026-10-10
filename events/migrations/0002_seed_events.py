from django.db import migrations

# The two events the site shipped with (mirrors fallbackEvents in the frontend).
EVENTS = [
    {
        'slug': 'afrigulf-2026',
        'title': 'AFRIGULF Exchange Global Business Summit 2026',
        'location': 'Dubai',
        'period': 'December 2026',
        'organiser': 'AFRIGULF Exchange initiative · Powered by TWB Global Tourism',
        'summary': 'Moving People, Trade and Capital Between Africa and the Gulf',
        'label': 'View Summit',
        'image': 'afrigulf-summit-image',
        'sort_order': 1,
    },
    {
        'slug': 'lccm-2026',
        'title': 'LCCM Global Leadership Summit 2026',
        'location': 'Dubai',
        'period': 'December 2026',
        'organiser': 'Organised by London College of Creative Media',
        'summary': 'Connect. Collaborate. Create Global Impact.',
        'label': 'View Event',
        'image': 'image-three',
        'sort_order': 2,
    },
]


def seed(apps, schema_editor):
    Event = apps.get_model('events', 'Event')
    for event in EVENTS:
        Event.objects.get_or_create(slug=event['slug'], defaults=event)


def unseed(apps, schema_editor):
    apps.get_model('events', 'Event').objects.filter(slug__in=[e['slug'] for e in EVENTS]).delete()


class Migration(migrations.Migration):
    dependencies = [('events', '0001_initial')]
    operations = [migrations.RunPython(seed, unseed)]
