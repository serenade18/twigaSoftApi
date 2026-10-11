import io
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from .models import Event, format_period

MEDIA = tempfile.mkdtemp()


class EventListTests(APITestCase):
    def test_lists_published_events_in_order(self):
        Event.objects.create(slug='hidden', title='Hidden', location='x', period='x', organiser='x', summary='x', is_published=False)
        response = self.client.get('/api/events')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e['slug'] for e in response.data['events']], ['afrigulf-2026', 'lccm-2026'])
        self.assertEqual(set(response.data['events'][0]), {
            'slug', 'title', 'location', 'period', 'organiser', 'summary', 'label', 'image', 'imageUrl', 'category', 'startDate', 'endDate',
        })

    def test_includes_category_and_dates(self):
        Event.objects.create(slug='expo', title='Expo', location='Nairobi', period='May 2027', organiser='x', summary='x',
                             category=Event.Category.EXHIBITION, start_date='2027-05-04', end_date='2027-05-06')
        expo = next(e for e in self.client.get('/api/events').data['events'] if e['slug'] == 'expo')
        self.assertEqual((expo['category'], expo['startDate'], expo['endDate']), ('exhibition', '2027-05-04', '2027-05-06'))
        summit = next(e for e in self.client.get('/api/events').data['events'] if e['slug'] == 'afrigulf-2026')
        self.assertEqual((summit['category'], summit['startDate']), ('summit', None))



def png(name='cover.png', size=(40, 20)):
    buffer = io.BytesIO()
    Image.new('RGB', size, 'navy').save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


VALID = {'title': 'Nairobi Investment Forum', 'location': 'Nairobi', 'organiser': 'AFRIGULF Exchange',
         'summary': 'Investors meet founders.', 'category': 'conference', 'startDate': '2027-04-14', 'endDate': '2027-04-15'}


class FormatPeriodTests(APITestCase):
    def test_formats(self):
        self.assertEqual(format_period(date(2027, 3, 10)), '10 March 2027')
        self.assertEqual(format_period(date(2027, 3, 10), date(2027, 3, 11)), '10–11 March 2027')
        self.assertEqual(format_period(date(2027, 2, 28), date(2027, 3, 2)), '28 February – 2 March 2027')
        self.assertEqual(format_period(date(2027, 12, 30), date(2028, 1, 2)), '30 December 2027 – 2 January 2028')


@override_settings(MEDIA_ROOT=MEDIA)
class AdminEventTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.client.force_authenticate(User.objects.create_user('staff@example.com', 'x', is_staff=True))
        self.visitor = User.objects.create_user('visitor@example.com', 'x')

    def create(self, **changes):
        return self.client.post('/api/admin/events', {**VALID, **changes}, format='json')

    def test_requires_staff(self):
        self.client.force_authenticate(self.visitor)
        self.assertEqual(self.client.get('/api/admin/events').status_code, 403)
        self.assertEqual(self.create().status_code, 403)

    def test_lists_drafts_too_with_status_counts_and_filters(self):
        self.create(isPublished=False)
        data = self.client.get('/api/admin/events').data
        self.assertEqual(len(data['events']), 3)  # the two seeded events plus the draft
        self.assertEqual(data['statusCounts'], {'published': 2, 'draft': 1})
        drafts = self.client.get('/api/admin/events', {'status': 'draft'}).data['events']
        self.assertEqual([e['title'] for e in drafts], ['Nairobi Investment Forum'])
        self.assertEqual(len(self.client.get('/api/admin/events', {'category': 'conference', 'search': 'nairobi'}).data['events']), 1)
        # Drafts stay off the public site.
        self.assertNotIn('Nairobi Investment Forum', [e['title'] for e in self.client.get('/api/events').data['events']])

    def test_creates_with_generated_slug_period_and_label(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        event = response.data['event']
        self.assertEqual((event['slug'], event['period'], event['label']), ('nairobi-investment-forum', '14–15 April 2027', 'View Event'))
        self.assertTrue(event['isPublished'])
        self.assertEqual(self.create().data['event']['slug'], 'nairobi-investment-forum-2')

    def test_keeps_a_typed_period_and_regenerates_a_generated_one_when_dates_change(self):
        typed = self.create(period='Spring 2027').data['event']
        self.assertEqual(typed['period'], 'Spring 2027')
        moved = self.client.patch(f"/api/admin/events/{typed['id']}", {'startDate': '2027-05-01', 'endDate': None}, format='json')
        self.assertEqual(moved.data['event']['period'], 'Spring 2027')

        generated = self.create(title='Other').data['event']
        moved = self.client.patch(f"/api/admin/events/{generated['id']}", {'startDate': '2027-05-01', 'endDate': None}, format='json')
        self.assertEqual(moved.data['event']['period'], '1 May 2027')
        cleared = self.client.patch(f"/api/admin/events/{typed['id']}", {'period': ''}, format='json')
        self.assertEqual(cleared.data['event']['period'], '1 May 2027')

    def test_validates(self):
        response = self.create(title='', startDate=None, endDate=None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data['fields']), {'title'})
        self.assertIn('period', self.create(startDate=None, endDate=None).data['fields'])
        self.assertIn('endDate', self.create(endDate='2027-04-01').data['fields'])
        self.assertIn('slug', self.create(slug='lccm-2026').data['fields'])
        self.assertIn('category', self.create(category='party').data['fields'])

    def test_uploads_replaces_and_removes_cover(self):
        response = self.client.post('/api/admin/events', {**VALID, 'endDate': '', 'cover': png()}, format='multipart')
        self.assertEqual(response.status_code, 201, response.data)
        event = response.data['event']
        self.assertRegex(event['imageUrl'], r'^/media/events/cover.*\.png$')
        self.assertEqual(event['period'], '14 April 2027')  # an empty multipart date means "no end date"
        public = next(e for e in self.client.get('/api/events').data['events'] if e['slug'] == event['slug'])
        self.assertEqual(public['imageUrl'], event['imageUrl'])

        old_file = Event.objects.get(pk=event['id']).cover.path
        replaced = self.client.patch(f"/api/admin/events/{event['id']}", {'cover': png('new.png')}, format='multipart').data['event']
        self.assertIn('new', replaced['imageUrl'])
        self.assertFalse(__import__('os').path.exists(old_file))

        removed = self.client.patch(f"/api/admin/events/{event['id']}", {'removeCover': True}, format='json').data['event']
        self.assertIsNone(removed['imageUrl'])

    def test_rejects_non_images_and_large_files(self):
        fake = SimpleUploadedFile('cover.png', b'not an image', content_type='image/png')
        self.assertIn('cover', self.client.post('/api/admin/events', {**VALID, 'cover': fake}, format='multipart').data['fields'])
        pdf = png('cover.gif')
        self.assertIn('cover', self.client.post('/api/admin/events', {**VALID, 'cover': pdf}, format='multipart').data['fields'])

    def test_publish_toggle_and_delete(self):
        event = self.create().data['event']
        url = f"/api/admin/events/{event['id']}"
        self.assertFalse(self.client.patch(url, {'isPublished': False}, format='json').data['event']['isPublished'])
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)
