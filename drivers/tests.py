import base64
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from bookings.tests import TODAY, make_vehicle
from fleet.models import Vehicle, VehicleCategory, VehicleServiceRecord, VehicleSubmission

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

    def test_marking_away_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.force_authenticate(user=self.driver.user)
        self.client.patch('/api/driver/away/', {'is_away': True, 'away_reason': 'On leave'}, format='json')
        notification = Notification.objects.get(event=NotificationEvent.DRIVER_AWAY)
        self.assertIn(self.driver.full_name, notification.message)
        self.assertIsNone(notification.organization_id)  # platform-wide, matches current email behavior

    def test_marking_away_again_while_already_away_does_not_notify_twice(self):
        from notifications.models import Notification, NotificationEvent

        self.client.force_authenticate(user=self.driver.user)
        self.client.patch('/api/driver/away/', {'is_away': True, 'away_reason': 'On leave'}, format='json')
        self.client.patch('/api/driver/away/', {'is_away': True, 'away_reason': 'Still on leave'}, format='json')
        self.assertEqual(Notification.objects.filter(event=NotificationEvent.DRIVER_AWAY).count(), 1)


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

    def test_submitting_a_vehicle_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        notification = Notification.objects.get(event=NotificationEvent.VEHICLE_SUBMISSION)
        self.assertIn(self.driver.full_name, notification.message)
        self.assertIsNone(notification.organization_id)

    def test_approving_a_submission_creates_a_vehicle_linked_to_the_driver(self):
        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        submission = VehicleSubmission.objects.get()

        submission.approve()

        self.assertEqual(submission.status, 'approved')
        self.assertEqual(submission.created_vehicle.driver_id, self.driver.id)
        self.assertTrue(submission.created_vehicle.is_available)
        self.assertFalse(submission.created_vehicle.is_company_owned)
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

    def test_approving_a_submission_notifies_the_driver_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        submission = VehicleSubmission.objects.get()
        submission.approve()
        notification = Notification.objects.get(event=NotificationEvent.VEHICLE_SUBMISSION_APPROVED)
        self.assertEqual(notification.driver_id, self.driver.id)

    def test_rejecting_a_submission_notifies_the_driver_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        submission = VehicleSubmission.objects.get()
        submission.reject(notes='Photos too dark')
        notification = Notification.objects.get(event=NotificationEvent.VEHICLE_SUBMISSION_REJECTED)
        self.assertEqual(notification.driver_id, self.driver.id)

    def test_no_submission_email_attempted_without_a_driver_email_on_file(self):
        self.assertEqual(self.driver.email, '')
        self.client.post('/api/driver/vehicle-submissions/', self._payload(), format='multipart')
        submission = VehicleSubmission.objects.get()

        mail.outbox = []
        submission.approve()
        self.assertEqual(len(mail.outbox), 0)


class DriverApplicationCreateTests(APITestCase):
    """The public 'become a driver' submission itself, separate from
    DriverApplicationThrottleTests (which only covers the rate limit)."""

    def _payload(self):
        category, _ = VehicleCategory.objects.get_or_create(
            slug='executive_suv_app', defaults={'name': 'Executive SUV App'},
        )
        return {
            'full_name': 'New Applicant', 'email': 'new-applicant@example.com', 'phone_number': '254700000000',
            'license_number': 'DL2', 'license_document': make_image('license.png'),
            'vehicle_name': 'Toyota Noah', 'vehicle_category': category.slug,
            'passenger_capacity': 7, 'price_per_day': 5000,
        }

    def test_submitting_an_application_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post('/api/drivers/apply/', self._payload(), format='multipart')
        notification = Notification.objects.get(event=NotificationEvent.DRIVER_APPLICATION)
        self.assertIn('New Applicant', notification.message)
        self.assertIsNone(notification.organization_id)

    def test_rejects_a_malformed_phone_number(self):
        payload = self._payload()
        payload['phone_number'] = '0712345678'  # leading 0, not the required 254 form
        response = self.client.post('/api/drivers/apply/', payload, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone_number', response.json())


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


class DriverVehicleServiceRecordTests(APITestCase):
    """A driver-partner logs their own vehicle's service history from the portal - gives admins
    a shared record without anyone having to ask. Scoped to vehicles the driver actually owns."""

    def setUp(self):
        driver_user = User.objects.create_user(username='service-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Service Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=driver_user)

    def test_driver_can_log_a_service_for_their_own_vehicle(self):
        response = self.client.post('/api/driver/service-records/', {
            'vehicle': self.vehicle.id, 'service_date': str(TODAY), 'notes': 'Oil change + filter',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        record = VehicleServiceRecord.objects.get()
        self.assertEqual(record.vehicle_id, self.vehicle.id)
        self.assertEqual(record.logged_by_id, self.driver.id)
        self.assertEqual(record.notes, 'Oil change + filter')

    def test_driver_cannot_log_a_service_for_another_drivers_vehicle(self):
        other_driver = Driver.objects.create(full_name='Other Driver', is_active=True)
        other_vehicle = make_vehicle(name='Other Car', driver=other_driver, price_per_day=Decimal('1000'))
        response = self.client.post('/api/driver/service-records/', {
            'vehicle': other_vehicle.id, 'service_date': str(TODAY), 'notes': 'Tyre change',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VehicleServiceRecord.objects.exists())

    def test_driver_cannot_log_a_service_for_a_company_owned_vehicle(self):
        company_vehicle = make_vehicle(name='Company Car', driver=None, price_per_day=Decimal('1000'))
        response = self.client.post('/api/driver/service-records/', {
            'vehicle': company_vehicle.id, 'service_date': str(TODAY), 'notes': 'Brake pads',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(VehicleServiceRecord.objects.exists())

    def test_driver_only_sees_service_records_for_their_own_vehicles(self):
        other_driver = Driver.objects.create(full_name='Other Driver', is_active=True)
        other_vehicle = make_vehicle(name='Other Car', driver=other_driver, price_per_day=Decimal('1000'))
        VehicleServiceRecord.objects.create(vehicle=self.vehicle, service_date=TODAY, notes='Mine')
        VehicleServiceRecord.objects.create(vehicle=other_vehicle, service_date=TODAY, notes='Not mine')

        response = self.client.get('/api/driver/service-records/')
        results = response.json()['results'] if 'results' in response.json() else response.json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['notes'], 'Mine')

    def test_service_records_appear_nested_on_the_driver_portal_profile(self):
        VehicleServiceRecord.objects.create(vehicle=self.vehicle, service_date=TODAY, notes='Oil change')
        response = self.client.get('/api/driver/me/')
        self.assertEqual(response.json()['vehicles'][0]['service_records'][0]['notes'], 'Oil change')

    def test_driver_sees_is_service_due_on_their_own_vehicle(self):
        old_created_at = timezone.now() - timedelta(days=Vehicle.SERVICE_DUE_INTERVAL_DAYS + 1)
        Vehicle.objects.filter(pk=self.vehicle.pk).update(created_at=old_created_at)
        response = self.client.get('/api/driver/me/')
        self.assertTrue(response.json()['vehicles'][0]['is_service_due'])

        VehicleServiceRecord.objects.create(vehicle=self.vehicle, service_date=TODAY)
        response = self.client.get('/api/driver/me/')
        self.assertFalse(response.json()['vehicles'][0]['is_service_due'])
