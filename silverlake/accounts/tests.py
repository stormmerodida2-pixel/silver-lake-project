from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from .services import blacklist_all_tokens_for_user

User = get_user_model()


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
