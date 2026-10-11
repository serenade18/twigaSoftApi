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
        self.admin = User.objects.create_user('admin@example.com', PASSWORD, is_staff=True, first_name='Ahmed')
        User.objects.create_user('visitor@example.com', PASSWORD)

    def login(self, email='admin@example.com', password=PASSWORD):
        return self.client.post('/api/admin/auth/login', {'email': email, 'password': password}, format='json')

    def test_login_returns_token_and_admin(self):
        response = self.login(email='ADMIN@example.com')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['token'], Token.objects.get(user=self.admin).key)
        self.assertEqual(response.data['admin'], {'id': str(self.admin.pk), 'email': 'admin@example.com', 'name': 'Ahmed', 'role': 'staff'})

    def test_login_rejects_wrong_password_unknown_email_and_non_staff(self):
        for email, password in [('admin@example.com', 'wrong'), ('nobody@example.com', PASSWORD), ('visitor@example.com', PASSWORD)]:
            response = self.login(email, password)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data['error'], 'Incorrect email or password.')

    def test_email_is_unique_ignoring_case(self):
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            get_user_model().objects.create_user('Admin@Example.com', PASSWORD)

    def test_create_superuser_is_staff(self):
        user = get_user_model().objects.create_superuser('owner@example.com', PASSWORD)
        self.assertTrue(user.is_staff and user.is_superuser)
        self.assertEqual(self.login('owner@example.com').status_code, 200)

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


class StaffManagementTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_superuser('owner@example.com', PASSWORD, first_name='Ahmed')
        self.staff = User.objects.create_user('staff@example.com', PASSWORD, is_staff=True, first_name='Zara')
        User.objects.create_user('visitor@example.com', PASSWORD)
        self.client.force_authenticate(self.owner)

    def test_me_reports_role(self):
        self.assertEqual(self.client.get('/api/admin/auth/me').data['admin']['role'], 'admin')
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/auth/me').data['admin']['role'], 'staff')

    def test_only_admins_manage_staff(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get('/api/admin/staff').status_code, 403)
        self.assertEqual(self.client.post('/api/admin/staff', {}, format='json').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get('/api/admin/staff').status_code, 401)

    def test_lists_portal_accounts_only(self):
        response = self.client.get('/api/admin/staff')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([m['email'] for m in response.data['staff']], ['owner@example.com', 'staff@example.com'])
        self.assertEqual(response.data['staff'][1]['role'], 'staff')
        self.assertNotIn('password', response.data['staff'][0])

    def test_creates_staff_who_can_sign_in(self):
        payload = {'email': 'new@example.com', 'firstName': 'Omar', 'lastName': 'Said', 'password': 'Welcome-pass-2026'}
        response = self.client.post('/api/admin/staff', payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual((response.data['member']['role'], response.data['member']['name']), ('staff', 'Omar Said'))
        self.client.force_authenticate(None)
        login = self.client.post('/api/admin/auth/login', {'email': 'new@example.com', 'password': 'Welcome-pass-2026'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data['admin']['role'], 'staff')

    def test_create_validates_email_and_password(self):
        taken = self.client.post('/api/admin/staff', {'email': 'STAFF@example.com', 'password': 'Welcome-pass-2026'}, format='json')
        self.assertEqual(taken.status_code, 400)
        self.assertIn('email', taken.data['fields'])
        for password in ['', 'password1', '12345678']:
            response = self.client.post('/api/admin/staff', {'email': 'x@example.com', 'password': password}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('password', response.data['fields'])

    def test_updates_role_and_deactivation_signs_out(self):
        token = Token.objects.create(user=self.staff)
        url = f'/api/admin/staff/{self.staff.pk}'
        self.assertEqual(self.client.patch(url, {'role': 'admin'}, format='json').data['member']['role'], 'admin')
        response = self.client.patch(url, {'isActive': False, 'firstName': 'Zee'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertEqual((self.staff.is_active, self.staff.is_superuser, self.staff.first_name), (False, True, 'Zee'))
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_password_change_signs_out(self):
        token = Token.objects.create(user=self.staff)
        self.client.patch(f'/api/admin/staff/{self.staff.pk}', {'password': 'Another-pass-2027'}, format='json')
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password('Another-pass-2027'))
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_admin_cannot_lock_themselves_out(self):
        url = f'/api/admin/staff/{self.owner.pk}'
        self.assertIn('role', self.client.patch(url, {'role': 'staff'}, format='json').data['fields'])
        self.assertIn('isActive', self.client.patch(url, {'isActive': False}, format='json').data['fields'])
        self.assertEqual(self.client.patch(url, {'firstName': 'A'}, format='json').status_code, 200)

    def test_non_portal_users_are_not_editable(self):
        visitor = get_user_model().objects.get(email='visitor@example.com')
        self.assertEqual(self.client.patch(f'/api/admin/staff/{visitor.pk}', {'role': 'admin'}, format='json').status_code, 404)
