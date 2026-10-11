import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from .models import Enquiry
from .views import AdminEnquiryListView

VALID = {
    'name': 'Amina Yusuf',
    'email': 'amina@example.com',
    'phone': '',
    'country': 'Kenya',
    'interest': 'Company Formation',
    'message': 'We would like to open a branch office in Dubai next year.',
    'website': '',
}


class EnquiryTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_creates_enquiry_and_returns_reference(self):
        response = self.client.post('/api/enquiries', VALID, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertRegex(response.data['reference'], r'^AGX-\d{6}-[A-Z2-9]{5}$')
        self.assertEqual(Enquiry.objects.get().reference, response.data['reference'])

    def test_accepts_footer_signup_payload_without_phone_or_honeypot(self):
        payload = {k: v for k, v in VALID.items() if k not in {'phone', 'website'}}
        self.assertEqual(self.client.post('/api/enquiries', payload, format='json').status_code, 201)

    def test_honeypot_pretends_success_without_saving(self):
        response = self.client.post('/api/enquiries', {**VALID, 'website': 'spam.example'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertTrue(re.match(r'^AGX-', response.data['reference']))
        self.assertFalse(Enquiry.objects.exists())

    def test_invalid_enquiry_returns_friendly_error(self):
        response = self.client.post('/api/enquiries', {**VALID, 'email': 'nope', 'name': ''}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'Please enter your full name.')
        self.assertEqual(set(response.data['fields']), {'name', 'email'})


class AdminEnquiryTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user('admin@example.com', 'pass', is_staff=True)
        self.visitor = User.objects.create_user('visitor@example.com', 'pass')
        self.client.force_authenticate(self.admin)
        fields = {k: v for k, v in VALID.items() if k != 'website'}
        self.amina = Enquiry.objects.create(**fields)
        self.omar = Enquiry.objects.create(**{**fields, 'name': 'Omar Said', 'email': 'omar@example.com', 'country': 'Oman'})
        self.closed = Enquiry.objects.create(**{**fields, 'name': 'Zara Ali', 'status': Enquiry.Status.CLOSED})

    def test_requires_staff(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/admin/enquiries').status_code, 401)
        self.client.force_authenticate(self.visitor)
        self.assertEqual(self.client.get('/api/admin/enquiries').status_code, 403)
        self.assertEqual(self.client.patch(f'/api/admin/enquiries/{self.amina.reference}', {'status': 'closed'}).status_code, 403)

    def test_lists_newest_first_with_status_counts(self):
        response = self.client.get('/api/admin/enquiries')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([e['name'] for e in response.data['enquiries']], ['Zara Ali', 'Omar Said', 'Amina Yusuf'])
        self.assertEqual(response.data['count'], 3)
        self.assertEqual(response.data['statusCounts'], {'new': 2, 'in_progress': 0, 'closed': 1})
        self.assertEqual(set(response.data['enquiries'][0]), {
            'reference', 'name', 'email', 'phone', 'country', 'interest', 'message', 'status', 'notes', 'createdAt',
        })

    def test_filters_by_status_and_search(self):
        response = self.client.get('/api/admin/enquiries', {'status': 'new', 'search': 'oman'})
        self.assertEqual([e['name'] for e in response.data['enquiries']], ['Omar Said'])
        # Counts follow the search but not the status filter.
        self.assertEqual(response.data['statusCounts'], {'new': 1, 'in_progress': 0, 'closed': 0})

    def test_paginates(self):
        with patch.object(AdminEnquiryListView, 'page_size', 2):
            response = self.client.get('/api/admin/enquiries', {'page': 2})
        self.assertEqual((response.data['page'], response.data['pages'], response.data['count']), (2, 2, 3))
        self.assertEqual([e['name'] for e in response.data['enquiries']], ['Amina Yusuf'])

    def test_detail_and_update_status_and_notes_only(self):
        url = f'/api/admin/enquiries/{self.amina.reference}'
        self.assertEqual(self.client.get(url).data['enquiry']['reference'], self.amina.reference)
        response = self.client.patch(url, {'status': 'in_progress', 'notes': 'Called back.', 'name': 'Changed'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.amina.refresh_from_db()
        self.assertEqual((self.amina.status, self.amina.notes, self.amina.name), ('in_progress', 'Called back.', 'Amina Yusuf'))

    def test_rejects_unknown_status_and_missing_enquiry(self):
        response = self.client.patch(f'/api/admin/enquiries/{self.amina.reference}', {'status': 'lost'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('status', response.data['fields'])
        self.assertEqual(self.client.get('/api/admin/enquiries/AGX-000000-XXXXX').status_code, 404)
