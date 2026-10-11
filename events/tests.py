import io
import shutil
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APITestCase

from .models import Booking, Event, EventDailyViews, format_period

MEDIA = tempfile.mkdtemp()


class EventListTests(APITestCase):
    def test_lists_published_events_in_order(self):
        Event.objects.create(slug='hidden', title='Hidden', location='x', period='x', organiser='x', summary='x', is_published=False)
        response = self.client.get('/api/events')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e['slug'] for e in response.data['events']], ['afrigulf-2026', 'lccm-2026'])
        self.assertEqual(set(response.data['events'][0]), {
            'slug', 'title', 'location', 'period', 'organiser', 'summary', 'label', 'image', 'imageUrl', 'category', 'startDate', 'endDate', 'isFeatured',
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


BOOKING = {'name': 'Amina Yusuf', 'email': 'amina@example.com', 'country': 'Kenya', 'attendees': 2, 'website': ''}


class BookingTests(APITestCase):
    def setUp(self):
        cache.clear()  # throttle counters
        self.event = Event.objects.create(slug='forum', title='Forum', location='Nairobi', organiser='x', summary='x',
                                          description='Day one.\n\nDay two.', start_date='2099-05-01', capacity=5)
        self.url = '/api/events/forum/bookings'

    def book(self, **changes):
        return self.client.post(self.url, {**BOOKING, **changes}, format='json')

    def test_event_detail_shows_booking_availability(self):
        data = self.client.get('/api/events/forum').data['event']
        self.assertEqual((data['description'], data['bookingsOpen'], data['seatsLeft'], data['maxAttendees']), ('Day one.\n\nDay two.', True, 5, 5))
        self.assertIsNone(data['closedReason'])
        Event.objects.filter(pk=self.event.pk).update(is_published=False)
        self.assertEqual(self.client.get('/api/events/forum').status_code, 404)

    def test_books_seats_and_emails_a_confirmation(self):
        with self.captureOnCommitCallbacks(execute=True):  # the email goes out once the booking is committed
            response = self.book()
        self.assertEqual(response.status_code, 201)
        self.assertRegex(response.data['reference'], r'^EVB-\d{6}-[A-Z2-9]{5}$')
        booking = Booking.objects.get()
        self.assertEqual((booking.event, booking.attendees, booking.status), (self.event, 2, 'confirmed'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['amina@example.com'])
        self.assertIn(booking.reference, mail.outbox[0].body)
        self.assertIn('nothing to pay', mail.outbox[0].body)
        self.assertEqual(self.client.get('/api/events/forum').data['event']['seatsLeft'], 3)

    def test_enforces_capacity_and_one_booking_per_email(self):
        self.assertEqual(self.book(attendees=4).status_code, 201)
        too_many = self.book(email='b@example.com', attendees=2)
        self.assertEqual(too_many.status_code, 400)
        self.assertEqual(too_many.data['fields']['attendees'], ['Only 1 seat left.'])
        duplicate = self.book(attendees=1)
        self.assertIn('email', duplicate.data['fields'])
        self.assertEqual(self.book(email='c@example.com', attendees=1).status_code, 201)
        full = self.book(email='d@example.com', attendees=1)
        self.assertEqual(full.data['error'], 'This event is fully booked.')
        self.assertEqual(self.client.get('/api/events/forum').data['event']['closedReason'], 'This event is fully booked.')

    def test_cancelled_bookings_free_their_seats(self):
        self.book(attendees=5)
        Booking.objects.update(status=Booking.Status.CANCELLED)
        self.assertEqual(self.book(attendees=5).status_code, 201)  # same email is fine once the old booking is cancelled

    def test_refuses_closed_past_and_unpublished_events(self):
        Event.objects.filter(pk=self.event.pk).update(bookings_open=False)
        self.assertEqual(self.book().data['error'], 'Bookings are closed for this event.')
        Event.objects.filter(pk=self.event.pk).update(bookings_open=True, start_date='2020-01-01')
        self.assertEqual(self.book().data['error'], 'This event has already taken place.')
        Event.objects.filter(pk=self.event.pk).update(is_published=False)
        self.assertEqual(self.book().status_code, 404)

    def test_validates_and_honeypot(self):
        response = self.book(name='', attendees=0)
        self.assertEqual(set(response.data['fields']), {'name', 'attendees'})
        self.assertIn('up to 20', self.book(attendees=21).data['fields']['attendees'][0])
        self.assertEqual(self.book(website='spam.example').status_code, 201)
        self.assertFalse(Booking.objects.exists())

    def test_counts_views_of_published_events(self):
        for _ in range(3):
            self.assertEqual(self.client.post('/api/events/forum/view').status_code, 204)
        self.client.post('/api/events/missing/view')
        self.event.refresh_from_db()
        self.assertEqual(self.event.view_count, 3)
        self.assertEqual(list(EventDailyViews.objects.values_list('views', flat=True)), [3])


class AdminBookingTests(APITestCase):
    def setUp(self):
        self.client.force_authenticate(get_user_model().objects.create_user('staff@example.com', 'x', is_staff=True))
        self.event = Event.objects.create(slug='forum', title='Forum', location='Nairobi', organiser='x', summary='x',
                                          start_date='2099-05-01', capacity=10, view_count=40)
        self.amina = Booking.objects.create(event=self.event, name='Amina', email='a@example.com', country='Kenya', attendees=3)
        Booking.objects.create(event=self.event, name='Omar', email='o@example.com', country='Oman', attendees=2, status='cancelled')

    def test_event_stats_in_admin_list_and_detail(self):
        listed = next(e for e in self.client.get('/api/admin/events').data['events'] if e['slug'] == 'forum')
        expected = {'views': 40, 'bookings': 1, 'seatsBooked': 3, 'seatsLeft': 7}
        self.assertEqual(listed['stats'], expected)
        self.assertEqual(self.client.get(f'/api/admin/events/{self.event.pk}').data['event']['stats'], expected)

    def test_lists_filters_and_exports_bookings(self):
        url = f'/api/admin/events/{self.event.pk}/bookings'
        data = self.client.get(url).data
        self.assertEqual([b['name'] for b in data['bookings']], ['Omar', 'Amina'])
        self.assertEqual(data['statusCounts'], {'confirmed': 1, 'cancelled': 1})
        self.assertEqual([b['name'] for b in self.client.get(url, {'status': 'confirmed', 'search': 'kenya'}).data['bookings']], ['Amina'])
        csv_response = self.client.get(url, {'export': 'csv'})
        self.assertEqual(csv_response['Content-Type'], 'text/csv; charset=utf-8')
        lines = csv_response.content.decode().splitlines()
        self.assertEqual(lines[0].split(',')[:3], ['Reference', 'Booked at', 'Status'])
        self.assertEqual(len(lines), 3)

    def test_cancels_and_restores_bookings_with_notes(self):
        url = f'/api/admin/bookings/{self.amina.reference}'
        response = self.client.patch(url, {'status': 'cancelled', 'notes': 'Asked to cancel.', 'attendees': 9}, format='json')
        self.assertEqual(response.status_code, 200)
        self.amina.refresh_from_db()
        self.assertEqual((self.amina.status, self.amina.notes, self.amina.attendees), ('cancelled', 'Asked to cancel.', 3))
        self.assertEqual(self.event.seats_left(), 10)

    def test_requires_staff(self):
        self.client.force_authenticate(get_user_model().objects.create_user('v@example.com', 'x'))
        self.assertEqual(self.client.get(f'/api/admin/events/{self.event.pk}/bookings').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/admin/bookings/{self.amina.reference}', {'status': 'cancelled'}).status_code, 403)


class AdminPerformanceTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.client.force_authenticate(User.objects.create_user('staff@example.com', 'x', is_staff=True))
        self.event = Event.objects.create(slug='forum', title='Forum', location='Nairobi', organiser='x', summary='x',
                                          start_date='2099-05-01', view_count=50)
        today = date.today()
        from datetime import timedelta
        EventDailyViews.objects.create(event=self.event, date=today, views=4)
        EventDailyViews.objects.create(event=self.event, date=today - timedelta(days=3), views=6)
        EventDailyViews.objects.create(event=self.event, date=today - timedelta(days=20), views=10)
        Booking.objects.create(event=self.event, name='A', email='a@example.com', country='x', attendees=3)
        Booking.objects.create(event=self.event, name='B', email='b@example.com', country='x', attendees=2, status='cancelled')

    def test_daily_views_and_seats(self):
        data = self.client.get(f'/api/admin/events/{self.event.pk}/performance').data
        self.assertEqual((data['days'], len(data['daily'])), (30, 30))
        self.assertEqual(data['daily'][-1], {'date': date.today().isoformat(), 'views': 4, 'bookings': 1, 'seats': 3})
        self.assertEqual(sum(d['views'] for d in data['daily']), 20)
        self.assertEqual(data['views'], {'total': 50, 'lastWeek': 10})
        self.assertEqual(data['bookings'], {'confirmed': 1, 'cancelled': 1, 'seats': 3})
        week = self.client.get(f'/api/admin/events/{self.event.pk}/performance', {'days': '7'}).data
        self.assertEqual(sum(d['views'] for d in week['daily']), 10)

    def test_all_bookings_list(self):
        other = Event.objects.create(slug='expo', title='Expo', location='x', organiser='x', summary='x', start_date='2099-01-01')
        Booking.objects.create(event=other, name='C', email='c@example.com', country='x')
        data = self.client.get('/api/admin/bookings').data
        self.assertEqual([b['name'] for b in data['bookings']], ['C', 'B', 'A'])
        self.assertEqual(data['statusCounts'], {'confirmed': 2, 'cancelled': 1})
        self.assertEqual([e['title'] for e in data['events']], ['Expo', 'Forum'])
        filtered = self.client.get('/api/admin/bookings', {'event': self.event.pk, 'status': 'confirmed'}).data
        self.assertEqual([b['name'] for b in filtered['bookings']], ['A'])
        self.assertEqual(filtered['bookings'][0]['eventTitle'], 'Forum')

    def test_featured_flag(self):
        response = self.client.patch(f'/api/admin/events/{self.event.pk}', {'isFeatured': True}, format='json')
        self.assertTrue(response.data['event']['isFeatured'])
        public = next(e for e in self.client.get('/api/events').data['events'] if e['slug'] == 'forum')
        self.assertTrue(public['isFeatured'])
