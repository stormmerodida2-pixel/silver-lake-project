import base64

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from fleet.models import VehicleCategory, VehicleSubmission

from .models import ApplicationStatus, Driver, DriverApplication
from .services import create_driver_login

User = get_user_model()

# A real 1x1 PNG - Pillow (used by ImageField validation) rejects arbitrary bytes.
PNG_1PX = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='
)


def make_image(name='photo.png'):
    return SimpleUploadedFile(name, PNG_1PX, content_type='image/png')


class CreateDriverLoginTests(TestCase):
    def test_creates_a_new_user_and_links_it_to_the_driver(self):
        driver = Driver.objects.create(full_name='New Driver', email='newdriver@example.com', is_active=True)
        create_driver_login(driver)
        driver.refresh_from_db()

        self.assertIsNotNone(driver.user_id)
        self.assertEqual(driver.user.username, 'newdriver@example.com')
        self.assertFalse(driver.user.has_usable_password())  # must set it via the invite link

    def test_reuses_an_existing_user_account_with_the_same_email(self):
        existing_user = User.objects.create_user(username='shared@example.com', password='pass12345!')
        driver = Driver.objects.create(full_name='Shared Account Driver', email='shared@example.com', is_active=True)

        create_driver_login(driver)
        driver.refresh_from_db()

        self.assertEqual(driver.user_id, existing_user.id)

    def test_does_nothing_without_an_email_on_file(self):
        driver = Driver.objects.create(full_name='No Email Driver', is_active=True)
        create_driver_login(driver)
        driver.refresh_from_db()
        self.assertIsNone(driver.user_id)

    def test_is_safe_to_call_again_for_a_driver_who_already_has_an_account(self):
        driver = Driver.objects.create(full_name='Repeat Invite', email='repeat@example.com', is_active=True)
        create_driver_login(driver)
        driver.refresh_from_db()
        first_user_id = driver.user_id

        create_driver_login(driver)  # e.g. admin clicks "Send Invite" again
        driver.refresh_from_db()
        self.assertEqual(driver.user_id, first_user_id)
        self.assertEqual(User.objects.filter(username='repeat@example.com').count(), 1)


class DriverApplicationApproveTests(TestCase):
    def _make_application(self):
        category, _ = VehicleCategory.objects.get_or_create(
            slug='premium_mpv', defaults={'name': 'Premium MPV'},
        )
        return DriverApplication.objects.create(
            full_name='Applicant One', email='applicant@example.com', phone_number='254700000000',
            license_number='DL999', license_document=make_image('license.png'),
            vehicle_name='Toyota Noah', vehicle_category=category,
            passenger_capacity=7, price_per_day=5000,
        )

    def test_approve_creates_a_linked_driver_and_vehicle_with_a_login(self):
        application = self._make_application()
        application.approve()

        self.assertEqual(application.status, ApplicationStatus.APPROVED)
        self.assertIsNotNone(application.created_driver)
        self.assertIsNotNone(application.created_vehicle)
        self.assertEqual(application.created_vehicle.driver_id, application.created_driver.id)
        self.assertIsNotNone(application.created_driver.user_id)

    def test_approve_is_idempotent(self):
        application = self._make_application()
        application.approve()
        first_driver_id = application.created_driver.id

        application.approve()  # should be a no-op, not create a second driver/vehicle
        self.assertEqual(application.created_driver.id, first_driver_id)

    def test_reject_records_notes_and_does_not_create_records(self):
        application = self._make_application()
        application.reject(notes='Vehicle photos were unclear')

        self.assertEqual(application.status, ApplicationStatus.REJECTED)
        self.assertEqual(application.review_notes, 'Vehicle photos were unclear')
        self.assertIsNone(application.created_driver)
        self.assertIsNone(application.created_vehicle)

    def test_reject_emails_the_applicant(self):
        application = self._make_application()
        mail.outbox = []
        application.reject(notes='Vehicle photos were unclear')

        rejection_emails = [m for m in mail.outbox if 'Update on your SilverLake driver application' in m.subject]
        self.assertEqual(len(rejection_emails), 1)
        self.assertIn('applicant@example.com', rejection_emails[0].to)


class DriverPortalAccessTests(APITestCase):
    """A plain customer account (no driver_profile) must not reach the driver portal API."""

    def setUp(self):
        self.customer = User.objects.create_user(username='customer@example.com', password='pass12345!')
        driver_user = User.objects.create_user(username='driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(
            user=driver_user, full_name='Portal Driver', email='driver@example.com', is_active=True,
        )

    def test_plain_customer_is_forbidden_from_driver_me(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/driver/me/')
        self.assertEqual(response.status_code, 403)

    def test_driver_can_view_their_own_profile(self):
        self.client.force_authenticate(user=self.driver.user)
        response = self.client.get('/api/driver/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['full_name'], 'Portal Driver')

    def test_suspended_driver_loses_portal_access(self):
        self.driver.is_active = False
        self.driver.save(update_fields=['is_active'])
        self.client.force_authenticate(user=self.driver.user)
        response = self.client.get('/api/driver/me/')
        self.assertEqual(response.status_code, 403)

    def test_driver_can_mark_themselves_away_with_a_reason(self):
        self.client.force_authenticate(user=self.driver.user)
        response = self.client.patch(
            '/api/driver/away/', {'is_away': True, 'away_reason': 'On leave'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.driver.refresh_from_db()
        self.assertTrue(self.driver.is_away)
        self.assertEqual(self.driver.away_reason, 'On leave')


class VehicleSubmissionTests(APITestCase):
    def setUp(self):
        driver_user = User.objects.create_user(username='driver2@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Submitting Driver', is_active=True)
        self.client.force_authenticate(user=driver_user)

    def _payload(self, image_count=2):
        return {
            'name': 'My Car', 'category': 'compact_sedan', 'passenger_capacity': 4,
            'price_per_day': '3000', 'logbook_document': SimpleUploadedFile('logbook.pdf', b'x'),
            'images': [make_image(f'{i}.png') for i in range(image_count)],
        }

    def test_submission_requires_at_least_two_photos(self):
        response = self.client.post('/api/driver/vehicle-submissions/', self._payload(image_count=1), format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_submission_with_two_photos_succeeds_and_stays_pending(self):
        response = self.client.post('/api/driver/vehicle-submissions/', self._payload(image_count=2), format='multipart')
        self.assertEqual(response.status_code, 201)
        submission = VehicleSubmission.objects.get()
        self.assertEqual(submission.status, 'pending')
        self.assertEqual(submission.photos.count(), 2)

    def test_approving_a_submission_creates_a_vehicle_linked_to_the_driver(self):
        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        submission = VehicleSubmission.objects.get()

        submission.approve()

        self.assertEqual(submission.status, 'approved')
        self.assertEqual(submission.created_vehicle.driver_id, self.driver.id)
        self.assertTrue(submission.created_vehicle.is_available)
        # First photo becomes the cover image, the rest become gallery images.
        self.assertEqual(submission.created_vehicle.gallery_images.count(), 1)

    def test_approving_a_submission_emails_the_driver(self):
        self.driver.email = 'submitting-driver@example.com'
        self.driver.save(update_fields=['email'])
        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        submission = VehicleSubmission.objects.get()

        mail.outbox = []
        submission.approve()
        approved_emails = [m for m in mail.outbox if 'is now live on SilverLake' in m.subject]
        self.assertEqual(len(approved_emails), 1)
        self.assertIn('submitting-driver@example.com', approved_emails[0].to)

    def test_rejecting_a_submission_emails_the_driver(self):
        self.driver.email = 'submitting-driver@example.com'
        self.driver.save(update_fields=['email'])
        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        submission = VehicleSubmission.objects.get()

        mail.outbox = []
        submission.reject(notes='Photos too dark')
        rejected_emails = [m for m in mail.outbox if 'Update on your My Car submission' in m.subject]
        self.assertEqual(len(rejected_emails), 1)
        self.assertIn('submitting-driver@example.com', rejected_emails[0].to)

    def test_no_submission_email_attempted_without_a_driver_email_on_file(self):
        self.assertEqual(self.driver.email, '')
        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        submission = VehicleSubmission.objects.get()

        mail.outbox = []
        submission.approve()
        self.assertEqual(len(mail.outbox), 0)


class DriverApplicationThrottleTests(APITestCase):
    """Public, unauthenticated, and accepts a file upload - previously had no rate limit at
    all, unlike registration/login/password-reset. settings.py forces every throttle scope to
    10000/min under 'test', so dial this one scope back down just to prove it's actually wired
    up, not just configured (mirrors accounts.tests.LoginThrottleTests)."""

    def _payload(self):
        category, _ = VehicleCategory.objects.get_or_create(
            slug='executive_suv', defaults={'name': 'Executive SUV'},
        )
        return {
            'full_name': 'Applicant', 'email': 'applicant@example.com', 'phone_number': '254700000000',
            'license_number': 'DL1', 'license_document': make_image('license.png'),
            'vehicle_name': 'Toyota Noah', 'vehicle_category': category.slug,
            'passenger_capacity': 7, 'price_per_day': 5000,
        }

    def test_repeated_applications_are_throttled(self):
        cache.clear()
        original = ScopedRateThrottle.THROTTLE_RATES.get('driver-application')
        ScopedRateThrottle.THROTTLE_RATES['driver-application'] = '2/min'
        try:
            for _ in range(2):
                self.client.post('/api/drivers/apply/', self._payload(), format='multipart')
            response = self.client.post('/api/drivers/apply/', self._payload(), format='multipart')
        finally:
            ScopedRateThrottle.THROTTLE_RATES['driver-application'] = original
        self.assertEqual(response.status_code, 429)
