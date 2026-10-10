from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .passwords import make_reset_token

PASSWORD = 'Original-pass-2026'


@override_settings(FRONTEND_URL='https://site.test')
class AdminAuthTests(APITestCase):
    def setUp(self):
        cache.clear()  # throttle counters
        User = get_user_model()
        self.admin = User.objects.create_user('ahmed', 'admin@example.com', PASSWORD, is_staff=True, first_name='Ahmed')
        User.objects.create_user('visitor', 'visitor@example.com', PASSWORD)

    def login(self, email='admin@example.com', password=PASSWORD):
        return self.client.post('/api/admin/auth/login', {'email': email, 'password': password}, format='json')

    def test_login_returns_token_and_admin(self):
        response = self.login(email='ADMIN@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['token'], Token.objects.get(user=self.admin).key)
        self.assertEqual(response.data['admin'], {'id': str(self.admin.pk), 'email': 'admin@example.com', 'name': 'Ahmed'})

    def test_login_rejects_wrong_password_unknown_email_and_non_staff(self):
        for email, password in [('admin@example.com', 'wrong'), ('nobody@example.com', PASSWORD), ('visitor@example.com', PASSWORD)]:
            response = self.login(email, password)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data['error'], 'Incorrect email or password.')

    def test_validation_errors_use_error_shape(self):
        response = self.client.post('/api/admin/auth/login', {'email': 'not-an-email'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)
        self.assertEqual(set(response.data['fields']), {'email', 'password'})

    def test_token_authenticates_until_logout(self):
        token = self.login().data['token']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(self.client.get('/api/admin/auth/me').data['admin']['email'], 'admin@example.com')
        self.assertEqual(self.client.post('/api/admin/auth/logout').status_code, 204)
        self.assertEqual(self.client.get('/api/admin/auth/me').status_code, 401)

    def test_expired_token_is_rejected(self):
        token = Token.objects.get(key=self.login().data['token'])
        Token.objects.filter(pk=token.pk).update(created=token.created - timedelta(hours=13))
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.key}')
        response = self.client.get('/api/admin/auth/me')
        self.assertEqual(response.status_code, 401)
        self.assertIn('expired', response.data['error'])

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get('/api/admin/auth/me').status_code, 401)

    def test_forgot_password_emails_admins_only_and_responds_the_same(self):
        responses = [self.client.post('/api/admin/auth/forgot-password', {'email': e}, format='json')
                     for e in ['admin@example.com', 'nobody@example.com', 'visitor@example.com']]
        self.assertEqual({r.status_code for r in responses}, {200})
        self.assertEqual(len({r.data['detail'] for r in responses}), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@example.com'])
        self.assertIn('https://site.test/admin/reset-password?token=', mail.outbox[0].body)

    def test_reset_password_sets_password_signs_out_and_is_single_use(self):
        old_token = self.login().data['token']
        self.admin.refresh_from_db()  # signing in changes last_login, which reset tokens depend on
        reset_token = make_reset_token(self.admin)
        response = self.client.post('/api/admin/auth/reset-password', {'token': reset_token, 'password': 'Brand-new-pass-77'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('Brand-new-pass-77'))
        self.assertFalse(Token.objects.filter(key=old_token).exists())
        reused = self.client.post('/api/admin/auth/reset-password', {'token': reset_token, 'password': 'Another-pass-88'}, format='json')
        self.assertEqual(reused.status_code, 400)
        self.assertEqual(reused.data['error'], 'This reset link is invalid or has expired.')

    def test_reset_password_rejects_bad_tokens_and_weak_or_same_passwords(self):
        for token in ['', 'garbage', 'MQ.not-a-real-token']:
            response = self.client.post('/api/admin/auth/reset-password', {'token': token, 'password': 'Brand-new-pass-77'}, format='json')
            self.assertEqual(response.status_code, 400)
        token = make_reset_token(self.admin)
        for password in ['password1', PASSWORD]:
            response = self.client.post('/api/admin/auth/reset-password', {'token': token, 'password': password}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('password', response.data['fields'])

    def test_login_is_throttled(self):
        statuses = [self.login(password='wrong').status_code for _ in range(11)]
        self.assertEqual(statuses[-1], 429)
