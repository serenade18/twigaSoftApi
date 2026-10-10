import re

from django.core.cache import cache
from rest_framework.test import APITestCase

from .models import Enquiry

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
