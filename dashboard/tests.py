from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from enquiries.models import Enquiry
from events.models import Event


def make_enquiry(days_ago=0, **fields):
    enquiry = Enquiry.objects.create(**{
        'name': 'Amina', 'email': 'a@example.com', 'country': 'Kenya', 'interest': 'Company Formation',
        'message': 'Hello there, we would like to talk.', **fields,
    })
    Enquiry.objects.filter(pk=enquiry.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    return enquiry


class StatsTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.client.force_authenticate(User.objects.create_user('staff@example.com', 'x', is_staff=True))
        User.objects.create_user('gone@example.com', 'x', is_staff=True, is_active=False)
        User.objects.create_user('visitor@example.com', 'x')
        Event.objects.create(slug='a', title='A', location='x', period='x', organiser='x', summary='x')
        Event.objects.create(slug='b', title='B', location='x', period='x', organiser='x', summary='x', is_published=False)
        make_enquiry(0)
        make_enquiry(2, country='Oman', status=Enquiry.Status.CLOSED)
        make_enquiry(3, country='Oman', interest='Trade Missions', status=Enquiry.Status.IN_PROGRESS)
        make_enquiry(10)  # outside 7 days, inside 30
        make_enquiry(40)  # previous 30-day period

    def test_requires_staff(self):
        self.client.force_authenticate(get_user_model().objects.get(email='visitor@example.com'))
        self.assertEqual(self.client.get('/api/admin/stats').status_code, 403)

    def test_default_30_day_stats(self):
        data = self.client.get('/api/admin/stats').data
        self.assertEqual(data['days'], 30)
        published = Event.objects.filter(is_published=True).count()  # includes events seeded by migrations
        self.assertEqual(data['totals'], {'enquiries': 5, 'awaitingReply': 3, 'publishedEvents': published, 'activeStaff': 1})
        self.assertEqual(data['period'], {'enquiries': 4, 'previous': 1})
        self.assertEqual(len(data['daily']), 30)
        self.assertEqual(data['daily'][-1], {'date': timezone.localdate().isoformat(), 'count': 1})
        self.assertEqual(sum(d['count'] for d in data['daily']), 4)
        self.assertEqual(data['byStatus'], {'new': 2, 'in_progress': 1, 'closed': 1})
        self.assertEqual(data['topCountries'], [{'label': 'Kenya', 'count': 2}, {'label': 'Oman', 'count': 2}])
        self.assertEqual(data['topInterests'][0], {'label': 'Company Formation', 'count': 3})
        self.assertEqual(len(data['recent']), 5)

    def test_range_scopes_period_figures(self):
        data = self.client.get('/api/admin/stats', {'days': '7'}).data
        self.assertEqual((data['days'], len(data['daily'])), (7, 7))
        self.assertEqual(data['period'], {'enquiries': 3, 'previous': 1})
        self.assertEqual(self.client.get('/api/admin/stats', {'days': '999'}).data['days'], 30)
