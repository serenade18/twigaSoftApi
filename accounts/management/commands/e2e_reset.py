import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError, call_command

from events.models import Event


class Command(BaseCommand):
    help = 'Resets the end-to-end test database and mail folder. Only runs with config.settings_e2e.'

    def add_arguments(self, parser):
        parser.add_argument('--admin', action='append', default=[], metavar='EMAIL:PASSWORD[:NAME]',
                            help='Create an admin (superuser); repeat for more.')
        parser.add_argument('--staff', action='append', default=[], metavar='EMAIL:PASSWORD[:NAME]',
                            help='Create a staff user (no staff management); repeat for more.')

    def handle(self, *args, **options):
        if not getattr(settings, 'E2E', False):
            raise CommandError('Refusing to wipe data: run with DJANGO_SETTINGS_MODULE=config.settings_e2e.')

        call_command('migrate', verbosity=0, interactive=False)
        call_command('flush', verbosity=0, interactive=False)  # also removes the seeded events
        Event.objects.create(
            slug='e2e-summit', title='E2E Investment Summit', location='Nairobi', period='March 2027',
            organiser='Organised by the E2E suite', summary='An event that only exists in the API database.',
            label='View E2E Summit', image=Event.Image.CENTRE, sort_order=1,
        )
        Event.objects.create(
            slug='e2e-hidden', title='Unpublished E2E Event', location='x', period='x', organiser='x',
            summary='x', is_published=False,
        )

        for option, is_superuser in [('admin', True), ('staff', False)]:
            for spec in options[option]:
                email, password, *rest = spec.split(':')
                first_name = rest[0] if rest else ''
                get_user_model().objects.create_user(email, password, is_staff=True, is_superuser=is_superuser, first_name=first_name)

        mail_dir = Path(settings.EMAIL_FILE_PATH)
        shutil.rmtree(mail_dir, ignore_errors=True)
        mail_dir.mkdir(parents=True)
        self.stdout.write('E2E database reset.')
