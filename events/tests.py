from rest_framework.test import APITestCase

from .models import Event


class EventListTests(APITestCase):
    def test_lists_published_events_in_order(self):
        Event.objects.create(slug='hidden', title='Hidden', location='x', period='x', organiser='x', summary='x', is_published=False)
        response = self.client.get('/api/events')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e['slug'] for e in response.data['events']], ['afrigulf-2026', 'lccm-2026'])
        self.assertEqual(set(response.data['events'][0]), {'slug', 'title', 'location', 'period', 'organiser', 'summary', 'label', 'image'})
