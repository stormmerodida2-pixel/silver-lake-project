import base64

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomerProfile
from .services import blacklist_all_tokens_for_user

User = get_user_model()

# A real 1x1 PNG - Pillow (used by ImageField validation) rejects arbitrary bytes.
PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


class RegistrationTests(APITestCase):
    def test_register_creates_an_inactive_user_with_separate_first_and_last_name(self):
        response = self.client.post('/api/auth/register/', {
            'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com',
            'phone_number': '254700000000', 'password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='jane@example.com')
        self.assertEqual(user.first_name, 'Jane')
        self.assertEqual(user.last_name, 'Doe')
        self.assertFalse(user.is_active)
        self.assertEqual(user.customer_profile.phone_number, '254700000000')

    def test_register_rejects_a_duplicate_email(self):
        User.objects.create_user(username='jane@example.com', email='jane@example.com', password='x')
        response = self.client.post('/api/auth/register/', {
            'first_name': 'Jane', 'last_name': 'Doe', 'email': 'jane@example.com',
            'phone_number': '254700000000', 'password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 400)

    def test_register_requires_both_names(self):
        response = self.client.post('/api/auth/register/', {
            'first_name': 'Jane', 'email': 'jane@example.com',
            'phone_number': '254700000000', 'password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('last_name', response.json())


class LoginThrottleTests(APITestCase):
    """settings.py forces every throttle scope to 10000/min under 'test' so the rest of the
    suite isn't tripped up by shared cache state - dial this one scope back down just for this
    test to prove the throttle is actually wired up, not just configured. ScopedRateThrottle
    reads its rates from a class attribute snapshotted at import time, so mutating it directly
    (rather than via override_settings, which doesn't reach an already-imported snapshot) is
    what actually takes effect here."""

    def test_login_is_throttled_after_repeated_failed_attempts(self):
        cache.clear()
        original = ScopedRateThrottle.THROTTLE_RATES.get('auth-login')
        ScopedRateThrottle.THROTTLE_RATES['auth-login'] = '2/min'
        try:
            for _ in range(2):
                self.client.post('/api/auth/login/', {'username': 'nobody@example.com', 'password': 'wrong'})
            response = self.client.post('/api/auth/login/', {'username': 'nobody@example.com', 'password': 'wrong'})
        finally:
            ScopedRateThrottle.THROTTLE_RATES['auth-login'] = original
        self.assertEqual(response.status_code, 429)


class LogoutTests(APITestCase):
    """Logging out previously only ever cleared the frontend's own localStorage - the token
    itself kept working against the API regardless. Now it's actually revoked server-side."""

    def setUp(self):
        self.user = User.objects.create_user(username='logout@example.com', password='pass12345!')

    def test_logout_blacklists_the_given_refresh_token(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/auth/logout/', {'refresh': str(refresh)})
        self.assertEqual(response.status_code, 200)

        refresh_response = self.client.post('/api/auth/refresh/', {'refresh': str(refresh)})
        self.assertEqual(refresh_response.status_code, 401)

    def test_logout_without_a_refresh_token_still_succeeds(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/auth/logout/', {})
        self.assertEqual(response.status_code, 200)

    def test_logout_with_a_garbage_token_does_not_crash(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/auth/logout/', {'refresh': 'not-a-real-token'})
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_user_cannot_call_logout(self):
        response = self.client.post('/api/auth/logout/', {'refresh': 'x'})
        self.assertEqual(response.status_code, 401)


class PasswordChangeInvalidatesSessionsTests(APITestCase):
    """A stolen token should stop working the moment a customer does the one thing they'd
    actually do if they suspected their account was compromised: change their password."""

    def setUp(self):
        self.user = User.objects.create_user(username='changepass@example.com', password='OldPass123!')

    def test_changing_password_blacklists_existing_refresh_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/auth/change-password/', {
            'old_password': 'OldPass123!', 'new_password': 'NewPass456!',
        })
        self.assertEqual(response.status_code, 200)

        refresh_response = self.client.post('/api/auth/refresh/', {'refresh': str(refresh)})
        self.assertEqual(refresh_response.status_code, 401)


class ProfileUpdateTests(APITestCase):
    """A customer editing their own name/phone via PATCH /auth/me/ - deliberately can't touch
    email (it doubles as the login username) or any of the staff/driver fields."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='profile@example.com', email='profile@example.com', password='pass12345!',
            first_name='Old', last_name='Name',
        )
        CustomerProfile.objects.create(user=self.user, phone_number='254700000000')
        self.client.force_authenticate(user=self.user)

    def test_can_update_name_and_phone_number(self):
        response = self.client.patch('/api/auth/me/', {
            'first_name': 'New', 'last_name': 'Name', 'phone_number': '254711111111',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['first_name'], 'New')
        self.assertEqual(response.json()['phone_number'], '254711111111')

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.customer_profile.phone_number, '254711111111')

    def test_partial_update_only_touches_the_given_fields(self):
        response = self.client.patch('/api/auth/me/', {'first_name': 'OnlyThis'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'OnlyThis')
        self.assertEqual(self.user.last_name, 'Name')  # unchanged
        self.assertEqual(self.user.customer_profile.phone_number, '254700000000')  # unchanged

    def test_cannot_update_email_via_profile(self):
        response = self.client.patch('/api/auth/me/', {'email': 'changed@example.com'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'profile@example.com')

    def test_cannot_grant_yourself_staff_via_profile(self):
        response = self.client.patch('/api/auth/me/', {'is_staff': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)

    def test_unauthenticated_user_cannot_update_a_profile(self):
        self.client.force_authenticate(user=None)
        response = self.client.patch('/api/auth/me/', {'first_name': 'X'}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_helper_is_safe_to_call_for_a_user_with_no_outstanding_tokens(self):
        blacklist_all_tokens_for_user(self.user)  # should not raise

    def test_confirming_a_password_reset_blacklists_existing_refresh_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        response = self.client.post('/api/auth/password-reset/confirm/', {
            'uid': uid, 'token': token, 'new_password': 'NewPass456!',
        })
        self.assertEqual(response.status_code, 200)

        refresh_response = self.client.post('/api/auth/refresh/', {'refresh': str(refresh)})
        self.assertEqual(refresh_response.status_code, 401)


class AvatarUploadTests(APITestCase):
    """A customer's profile photo - separate POST-to-set/DELETE-to-remove endpoints rather than
    bundled into the plain-JSON PATCH /auth/me/, since HTML/multipart forms can't represent
    "clear this field" the way an explicit DELETE can."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='avatar@example.com', email='avatar@example.com', password='pass12345!',
        )
        self.client.force_authenticate(user=self.user)

    def _png(self, name='avatar.png'):
        return SimpleUploadedFile(name, PNG_1PX, content_type='image/png')

    def test_avatar_is_null_by_default(self):
        response = self.client.get('/api/auth/me/')
        self.assertIsNone(response.json()['avatar'])

    def test_can_upload_an_avatar(self):
        response = self.client.post('/api/auth/me/avatar/', {'avatar': self._png()}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()['avatar'])
        self.user.customer_profile.refresh_from_db()
        self.assertTrue(self.user.customer_profile.avatar)

    def test_uploading_again_replaces_the_previous_avatar(self):
        self.client.post('/api/auth/me/avatar/', {'avatar': self._png('first.png')}, format='multipart')
        self.user.customer_profile.refresh_from_db()
        first_file = self.user.customer_profile.avatar
        first_name = first_file.name
        self.assertTrue(first_file.storage.exists(first_name))

        self.client.post('/api/auth/me/avatar/', {'avatar': self._png('second.png')}, format='multipart')
        self.user.customer_profile.refresh_from_db()
        self.assertNotEqual(self.user.customer_profile.avatar.name, first_name)
        # The old file shouldn't just be orphaned on disk once nothing references it anymore.
        self.assertFalse(first_file.storage.exists(first_name))

    def test_can_remove_an_avatar(self):
        self.client.post('/api/auth/me/avatar/', {'avatar': self._png()}, format='multipart')
        response = self.client.delete('/api/auth/me/avatar/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['avatar'])
        self.user.customer_profile.refresh_from_db()
        self.assertFalse(self.user.customer_profile.avatar)

    def test_removing_with_no_avatar_set_is_a_harmless_no_op(self):
        response = self.client.delete('/api/auth/me/avatar/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['avatar'])

    def test_upload_with_no_file_is_a_clean_400(self):
        response = self.client.post('/api/auth/me/avatar/', {}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_oversized_avatar_is_rejected(self):
        oversized = SimpleUploadedFile('big.png', PNG_1PX + b'0' * (6 * 1024 * 1024), content_type='image/png')
        response = self.client.post('/api/auth/me/avatar/', {'avatar': oversized}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('avatar', response.json())

    def test_a_rejected_replacement_does_not_delete_the_existing_avatar(self):
        self.client.post('/api/auth/me/avatar/', {'avatar': self._png()}, format='multipart')
        self.user.customer_profile.refresh_from_db()
        existing_name = self.user.customer_profile.avatar.name

        oversized = SimpleUploadedFile('big.png', PNG_1PX + b'0' * (6 * 1024 * 1024), content_type='image/png')
        response = self.client.post('/api/auth/me/avatar/', {'avatar': oversized}, format='multipart')
        self.assertEqual(response.status_code, 400)

        self.user.customer_profile.refresh_from_db()
        self.assertEqual(self.user.customer_profile.avatar.name, existing_name)
        self.assertTrue(self.user.customer_profile.avatar.storage.exists(existing_name))

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.post('/api/auth/me/avatar/', {'avatar': self._png()}, format='multipart')
        self.assertEqual(response.status_code, 401)

    def test_avatar_appears_in_the_login_response(self):
        self.client.post('/api/auth/me/avatar/', {'avatar': self._png()}, format='multipart')
        self.client.force_authenticate(user=None)
        response = self.client.post('/api/auth/login/', {'username': 'avatar@example.com', 'password': 'pass12345!'})
        self.assertIsNotNone(response.json()['user']['avatar'])
