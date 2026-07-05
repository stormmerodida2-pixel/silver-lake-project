from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

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
