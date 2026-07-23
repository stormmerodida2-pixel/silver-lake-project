from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image as PILImage
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CustomerProfile
from bookings.models import Booking, BookingStatus
from bookings.tests import NEXT_WEEK, TOMORROW, make_booking, make_vehicle
from drivers.models import Driver, DriverApplication
from fleet.models import FleetPartner, Vehicle, VehicleCategory, VehicleImage, VehicleServiceRecord, VehicleSubmission
from payments.models import DriverPayout, Payment, PaymentMethod, PaymentStatus, Refund

from .models import AuditLog, ClientErrorReport, StaffOrganization
from .utils import parse_amount
from .validators import validate_kenyan_phone_number

User = get_user_model()


class KenyanPhoneValidatorTests(TestCase):
    def test_accepts_a_valid_safaricom_style_number(self):
        validate_kenyan_phone_number('254712345678')  # does not raise

    def test_accepts_a_valid_254_one_range_number(self):
        validate_kenyan_phone_number('254112345678')  # does not raise

    def test_rejects_a_leading_zero_instead_of_254(self):
        with self.assertRaises(ValidationError):
            validate_kenyan_phone_number('0712345678')

    def test_rejects_a_leading_plus(self):
        with self.assertRaises(ValidationError):
            validate_kenyan_phone_number('+254712345678')

    def test_rejects_too_few_digits(self):
        with self.assertRaises(ValidationError):
            validate_kenyan_phone_number('25471234567')

    def test_rejects_too_many_digits(self):
        with self.assertRaises(ValidationError):
            validate_kenyan_phone_number('2547123456789')

    def test_rejects_a_non_mobile_network_prefix(self):
        with self.assertRaises(ValidationError):
            validate_kenyan_phone_number('254212345678')

    def test_rejects_an_empty_value(self):
        with self.assertRaises(ValidationError):
            validate_kenyan_phone_number('')

    def test_rejects_none(self):
        with self.assertRaises(ValidationError):
            validate_kenyan_phone_number(None)


class AdminPayoutVerificationTests(APITestCase):
    """A payout confirmed via self-reported cash must be explicitly verified by a superadmin
    before it can be marked paid - closes the gap where a fabricated cash claim would otherwise
    sail straight through to a real payout."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff@example.com', password='pass12345!', is_staff=True)

        self.driver = Driver.objects.create(full_name='Payout Driver', is_active=True)
        vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=self.driver, status=BookingStatus.PENDING)

        self.cash_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )
        self.booking.confirm_if_deposit_met()
        self.payout = DriverPayout.objects.get(booking=self.booking)
        assert self.payout.needs_verification and not self.payout.is_verified

    def _log_deposit(self):
        from payments.models import CashDeposit
        CashDeposit.objects.create(
            payment=self.cash_payment, amount=self.cash_payment.amount,
            mpesa_reference='QWERTY123', logged_by=self.driver,
        )

    def test_cannot_mark_paid_before_verifying(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{self.payout.id}/mark-paid/')
        self.assertEqual(response.status_code, 400)
        self.payout.refresh_from_db()
        self.assertFalse(self.payout.is_paid)

    def test_support_staff_cannot_verify_a_payout(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/admin/payouts/{self.payout.id}/verify/')
        self.assertEqual(response.status_code, 403)

    def test_superadmin_can_verify_then_mark_paid(self):
        self._log_deposit()
        self.client.force_authenticate(user=self.superadmin)

        verify_response = self.client.post(
            f'/api/admin/payouts/{self.payout.id}/verify/',
            {'note': 'Called customer, confirmed amount received.'}, format='json',
        )
        self.assertEqual(verify_response.status_code, 200)
        self.payout.refresh_from_db()
        self.assertTrue(self.payout.is_verified)
        self.assertIsNotNone(self.payout.verified_at)
        self.assertEqual(self.payout.verification_note, 'Called customer, confirmed amount received.')

        pay_response = self.client.post(
            f'/api/admin/payouts/{self.payout.id}/mark-paid/', {'payout_reference': 'MPESA123'},
        )
        self.assertEqual(pay_response.status_code, 200)
        self.payout.refresh_from_db()
        self.assertTrue(self.payout.is_paid)

        from notifications.models import Notification, NotificationEvent
        notification = Notification.objects.get(event=NotificationEvent.PAYOUT_PAID)
        self.assertEqual(notification.driver_id, self.driver.id)

    def test_verifying_without_a_note_is_rejected(self):
        self._log_deposit()
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{self.payout.id}/verify/', {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.payout.refresh_from_db()
        self.assertFalse(self.payout.is_verified)

    def test_verifying_with_a_blank_note_is_rejected(self):
        self._log_deposit()
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{self.payout.id}/verify/', {'note': '   '}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_cannot_verify_without_a_matching_cash_deposit(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(
            f'/api/admin/payouts/{self.payout.id}/verify/', {'note': 'Confirmed with customer.'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.payout.refresh_from_db()
        self.assertFalse(self.payout.is_verified)

    def test_marking_a_payout_paid_emails_the_driver(self):
        self._log_deposit()
        self.driver.email = 'payout-driver@example.com'
        self.driver.save(update_fields=['email'])
        self.client.force_authenticate(user=self.superadmin)
        self.client.post(f'/api/admin/payouts/{self.payout.id}/verify/', {'note': 'Confirmed with customer.'}, format='json')

        mail.outbox = []
        self.client.post(f'/api/admin/payouts/{self.payout.id}/mark-paid/', {'payout_reference': 'MPESA123'})
        payout_emails = [m for m in mail.outbox if 'payout has been paid' in m.subject]
        self.assertEqual(len(payout_emails), 1)
        self.assertIn('payout-driver@example.com', payout_emails[0].to)

    def test_marking_an_organization_payout_paid_notifies_that_orgs_admin_in_app(self):
        # An organization-owned vehicle's payout has no driver_id at all - the notification has
        # to target organization instead, or it silently never reaches anyone's admin dashboard.
        from notifications.models import Notification, NotificationEvent

        partner = FleetPartner.objects.create(name='Payout Notify Co', platform_fee_percent=Decimal('10'))
        vehicle = make_vehicle(name='Org Payout Car', owner=partner, is_company_owned=False)
        customer = User.objects.create_user(username='org-payout-client@example.com', password='pass12345!')
        booking = make_booking(customer, vehicle, status=BookingStatus.PENDING)
        Payment.objects.create(booking=booking, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL)
        booking.confirm_if_deposit_met()
        payout = DriverPayout.objects.get(booking=booking)
        self.assertIsNone(payout.driver_id)
        self.assertEqual(payout.organization_id, partner.id)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{payout.id}/mark-paid/', {'payout_reference': 'MPESA456'})
        self.assertEqual(response.status_code, 200)

        notification = Notification.objects.get(event=NotificationEvent.PAYOUT_PAID, organization_id=partner.id)
        self.assertIn('KES', notification.message)
        self.assertEqual(notification.link_path, '/admin/payouts')

    def test_mpesa_sourced_payout_can_be_marked_paid_without_verification(self):
        other_customer = User.objects.create_user(username='other-client@example.com', password='pass12345!')
        other_vehicle = make_vehicle(name='Other Car', driver=self.driver, price_per_day=Decimal('1000'))
        other_booking = make_booking(other_customer, other_vehicle, driver=self.driver, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=other_booking, method=PaymentMethod.MPESA,
            amount=other_booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        other_booking.confirm_if_deposit_met()
        other_payout = DriverPayout.objects.get(booking=other_booking)
        self.assertFalse(other_payout.needs_verification)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{other_payout.id}/mark-paid/')
        self.assertEqual(response.status_code, 200)

    def test_card_sourced_payout_also_needs_verification(self):
        # Card has no independent gateway confirming it either (no live processor is wired up),
        # so it goes through the same self-reported verification gate as cash.
        other_customer = User.objects.create_user(username='card-client@example.com', password='pass12345!')
        other_vehicle = make_vehicle(name='Card Car', driver=self.driver, price_per_day=Decimal('1000'))
        other_booking = make_booking(other_customer, other_vehicle, driver=self.driver, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=other_booking, method=PaymentMethod.CARD,
            amount=other_booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        other_booking.confirm_if_deposit_met()
        other_payout = DriverPayout.objects.get(booking=other_booking)
        self.assertTrue(other_payout.needs_verification)

        # Card doesn't need a Paybill deposit logged (no physical cash involved) - only the
        # generic verification note is required, unlike cash.
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(
            f'/api/admin/payouts/{other_payout.id}/verify/', {'note': 'Confirmed card payment.'}, format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_cannot_mark_paid_a_voided_payout(self):
        self.payout.is_verified = True
        self.payout.void()
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/payouts/{self.payout.id}/mark-paid/')
        self.assertEqual(response.status_code, 400)


class AdminRefundActionTests(APITestCase):
    """A refund gets auto-created when a paid booking is cancelled (see bookings.tests); this
    covers admin's ability to see and act on it."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super2@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff2@example.com', password='pass12345!', is_staff=True)
        vehicle = make_vehicle(name='Refund Car', price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='refund-client@example.com', password='pass12345!')
        booking = make_booking(
            self.customer, vehicle, status=BookingStatus.PENDING, customer_email='refund-client@example.com',
        )
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.mark_cancelled()
        self.refund = Refund.objects.get(booking=booking)

    def test_support_staff_can_list_refunds(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/refunds/')
        self.assertEqual(response.status_code, 200)

    def test_support_staff_cannot_mark_a_refund_issued(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/admin/refunds/{self.refund.id}/mark-issued/')
        self.assertEqual(response.status_code, 403)

    def test_superadmin_can_mark_a_refund_issued(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/refunds/{self.refund.id}/mark-issued/', {'reference': 'MPESA-REFUND-1'})
        self.assertEqual(response.status_code, 200)
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.status, 'issued')
        self.assertEqual(self.refund.reference, 'MPESA-REFUND-1')
        self.assertIsNotNone(self.refund.issued_at)

    def test_cannot_mark_a_refund_issued_without_a_reference(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/refunds/{self.refund.id}/mark-issued/')
        self.assertEqual(response.status_code, 400)
        self.refund.refresh_from_db()
        self.assertNotEqual(self.refund.status, 'issued')

    def test_cannot_mark_a_refund_issued_with_a_reference_shorter_than_4_characters(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/refunds/{self.refund.id}/mark-issued/', {'reference': 'abc'})
        self.assertEqual(response.status_code, 400)
        self.refund.refresh_from_db()
        self.assertNotEqual(self.refund.status, 'issued')

    def test_marking_a_refund_issued_emails_the_customer(self):
        self.client.force_authenticate(user=self.superadmin)
        mail.outbox = []
        self.client.post(f'/api/admin/refunds/{self.refund.id}/mark-issued/', {'reference': 'MPESA-REFUND-1'})
        refund_emails = [m for m in mail.outbox if 'refund has been issued' in m.subject]
        self.assertEqual(len(refund_emails), 1)
        self.assertIn('refund-client@example.com', refund_emails[0].to)

    def test_marking_a_refund_issued_notifies_the_client_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.force_authenticate(user=self.superadmin)
        self.client.post(f'/api/admin/refunds/{self.refund.id}/mark-issued/', {'reference': 'MPESA-REFUND-1'})
        notification = Notification.objects.get(event=NotificationEvent.REFUND_ISSUED)
        self.assertEqual(notification.user_id, self.customer.id)


class AdminDriverCashToggleTests(APITestCase):
    """Only a genuine superadmin can force a driver onto M-Pesa/card only (see
    Driver.cash_payments_enabled, enforced in payments.services.declare_offline_payment) -
    matches this app's usual bar for anything that changes how a driver gets paid."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='cash-toggle-super@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='cash-toggle-staff@example.com', password='pass12345!', is_staff=True)
        self.driver = Driver.objects.create(full_name='Toggle Driver', is_active=True)

    def test_defaults_to_disabled(self):
        # Opt-in, not opt-out - a newly registered driver can't accept cash until a superadmin
        # explicitly turns it on for them.
        self.assertFalse(self.driver.cash_payments_enabled)

    def test_superadmin_can_enable_cash_for_a_driver(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/drivers/{self.driver.id}/', {'cash_payments_enabled': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.driver.refresh_from_db()
        self.assertTrue(self.driver.cash_payments_enabled)

    def test_support_staff_cannot_toggle_it(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(f'/api/admin/drivers/{self.driver.id}/', {'cash_payments_enabled': True}, format='json')
        self.assertEqual(response.status_code, 403)
        self.driver.refresh_from_db()
        self.assertFalse(self.driver.cash_payments_enabled)


class AdminAuditLogTests(APITestCase):
    """Sensitive admin actions (role changes, suspensions, payouts, refunds) must leave a
    record of who did them - otherwise a two-tier permission system can't answer 'who did this'."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super3@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff3@example.com', password='pass12345!', is_staff=True)

    def test_suspending_a_driver_is_logged(self):
        driver = Driver.objects.create(full_name='Logged Driver', is_active=True)
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/drivers/{driver.id}/suspend/', {'reason': 'Complaint received'})

        entry = AuditLog.objects.get(action='driver.suspend')
        self.assertEqual(entry.actor, self.staff)
        self.assertEqual(entry.target_repr, driver.full_name)
        self.assertEqual(entry.detail, 'Complaint received')

    def test_promoting_a_user_to_staff_is_logged(self):
        target = User.objects.create_user(username='promote-me@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/users/{target.id}/', {'is_staff': True}, format='json')

        entry = AuditLog.objects.get(action='user.update_roles')
        self.assertEqual(entry.actor, self.superadmin)
        self.assertIn('is_staff=True', entry.detail)

    def test_editing_a_user_without_changing_roles_is_not_logged(self):
        target = User.objects.create_user(username='no-role-change@example.com', password='pass12345!', first_name='Old')
        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/users/{target.id}/', {'first_name': 'New'}, format='json')

        self.assertFalse(AuditLog.objects.filter(action='user.update_roles').exists())

    def test_unauthenticated_user_cannot_view_the_audit_log(self):
        response = self.client.get('/api/admin/audit-log/')
        self.assertEqual(response.status_code, 401)

    def test_reassigning_a_bookings_driver_is_logged(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='audit-client@example.com', password='pass12345!')
        booking = make_booking(customer, vehicle, status=BookingStatus.PENDING)
        driver = Driver.objects.create(full_name='Audit Driver', is_active=True)

        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/bookings/{booking.id}/', {'driver': driver.id}, format='json')

        entry = AuditLog.objects.get(action='booking.update')
        self.assertEqual(entry.actor, self.superadmin)
        self.assertIn(str(driver.id), entry.detail)

    def test_creating_a_vehicle_is_logged(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(
            '/api/admin/fleet/',
            {'name': 'Audited Car', 'category': 'compact_sedan', 'passenger_capacity': 4, 'price_per_day': '1000'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(AuditLog.objects.filter(action='vehicle.create').exists())

    def test_updating_a_vehicle_is_logged(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'price_per_day': '1200'}, format='json')
        self.assertTrue(AuditLog.objects.filter(action='vehicle.update').exists())

    def test_adding_a_gallery_image_is_logged(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.superadmin)
        self.client.post(
            f'/api/admin/fleet/{vehicle.id}/gallery/',
            {'images': [SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg')]}, format='multipart',
        )
        self.assertTrue(AuditLog.objects.filter(action='vehicle.add_gallery_images').exists())

    def test_removing_a_gallery_image_is_logged(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        image = VehicleImage.objects.create(
            vehicle=vehicle, image=SimpleUploadedFile('a.jpg', b'x', content_type='image/jpeg'),
        )
        self.client.force_authenticate(user=self.superadmin)
        self.client.delete(f'/api/admin/fleet/{vehicle.id}/gallery/{image.id}/')
        self.assertTrue(AuditLog.objects.filter(action='vehicle.remove_gallery_image').exists())

    def test_approving_a_review_is_logged(self):
        from reviews.models import Review

        review = Review.objects.create(customer_name='Jane', rating=5, comment='Great!', is_approved=False)
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/reviews/{review.id}/approve/')
        self.assertTrue(AuditLog.objects.filter(action='review.approve').exists())

    def test_deleting_a_review_is_logged(self):
        from reviews.models import Review

        review = Review.objects.create(customer_name='Jane', rating=5, comment='Great!', is_approved=True)
        self.client.force_authenticate(user=self.superadmin)
        self.client.delete(f'/api/admin/reviews/{review.id}/')
        self.assertTrue(AuditLog.objects.filter(action='review.delete').exists())

    def test_approving_a_driver_application_is_logged(self):
        from drivers.models import DriverApplication

        category, _ = VehicleCategory.objects.get_or_create(
            slug='premium_mpv', defaults={'name': 'Premium MPV'},
        )
        application = DriverApplication.objects.create(
            full_name='Applicant', email='applicant@example.com', phone_number='254700000000',
            license_number='DL1', license_document=SimpleUploadedFile('l.jpg', b'x', content_type='image/jpeg'),
            vehicle_name='Toyota Noah', vehicle_category=category,
            passenger_capacity=7, price_per_day=5000,
        )
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/driver-applications/{application.id}/approve/')
        self.assertTrue(AuditLog.objects.filter(action='driver_application.approve').exists())

    def test_approving_a_vehicle_submission_is_logged(self):
        from fleet.models import VehicleSubmission

        driver = Driver.objects.create(full_name='Submitting Driver', is_active=True)
        category, _ = VehicleCategory.objects.get_or_create(
            slug='premium_mpv', defaults={'name': 'Premium MPV'},
        )
        submission = VehicleSubmission.objects.create(
            driver=driver, name='Submitted Car', category=category,
            passenger_capacity=7, price_per_day=5000,
            logbook_document=SimpleUploadedFile('logbook.pdf', b'x', content_type='application/pdf'),
        )
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/vehicle-submissions/{submission.id}/approve/')
        self.assertTrue(AuditLog.objects.filter(action='vehicle_submission.approve').exists())

    def test_action_on_an_org_owned_vehicle_logs_that_organization(self):
        organization = FleetPartner.objects.create(name='Audit Org', platform_fee_percent=Decimal('10'))
        vehicle = make_vehicle(name='Audit Org Car', price_per_day=Decimal('1000'), owner=organization)
        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'price_per_day': '1200'}, format='json')

        entry = AuditLog.objects.get(action='vehicle.update')
        self.assertEqual(entry.organization_id, organization.id)

    def test_action_with_no_derivable_organization_stays_platform_only(self):
        driver = Driver.objects.create(full_name='No-Org Driver', is_active=True)
        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/admin/drivers/{driver.id}/suspend/', {'reason': 'test'})

        entry = AuditLog.objects.get(action='driver.suspend')
        self.assertIsNone(entry.organization)

    def test_action_on_a_company_owned_vehicles_booking_logs_no_organization(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='audit-no-org-client@example.com', password='pass12345!')
        booking = make_booking(customer, vehicle, status=BookingStatus.PENDING)
        driver = Driver.objects.create(full_name='No-Org Booking Driver', is_active=True)

        self.client.force_authenticate(user=self.superadmin)
        self.client.patch(f'/api/admin/bookings/{booking.id}/', {'driver': driver.id}, format='json')

        entry = AuditLog.objects.get(action='booking.update')
        self.assertIsNone(entry.organization)


class CascadeDeleteProtectionTests(APITestCase):
    """Deleting a user/driver/vehicle must never silently take their bookings/payouts with
    them - that's exactly the financial trail the rest of this app is built to preserve."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super4@example.com', password='pass12345!')

    def test_deleting_a_user_with_bookings_is_blocked(self):
        customer = User.objects.create_user(username='has-bookings@example.com', password='pass12345!')
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        make_booking(customer, vehicle, status=BookingStatus.PENDING)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/users/{customer.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(id=customer.id).exists())

    def test_deleting_a_user_with_no_bookings_still_works(self):
        customer = User.objects.create_user(username='no-bookings@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/users/{customer.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(User.objects.filter(id=customer.id).exists())

    def test_deleting_a_driver_with_payouts_is_blocked(self):
        driver = Driver.objects.create(full_name='Payout History Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='payout-client@example.com', password='pass12345!')
        booking = make_booking(customer, vehicle, driver=driver, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()
        self.assertTrue(DriverPayout.objects.filter(driver=driver).exists())

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/drivers/{driver.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Driver.objects.filter(id=driver.id).exists())
        self.assertTrue(DriverPayout.objects.filter(driver=driver).exists())

    def test_deleting_a_driver_with_no_payouts_still_works(self):
        driver = Driver.objects.create(full_name='Clean Driver', is_active=True)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/drivers/{driver.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Driver.objects.filter(id=driver.id).exists())

    def test_deleting_a_vehicle_with_bookings_is_blocked(self):
        customer = User.objects.create_user(username='vehicle-client@example.com', password='pass12345!')
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        make_booking(customer, vehicle, status=BookingStatus.PENDING)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet/{vehicle.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('bookings on file', response.json()['detail'])


class AdminVehicleDriverAssignmentTests(APITestCase):
    """Admin needs to be able to say who drives a company-owned vehicle - otherwise a
    with-driver booking on it never has a driver to notify, pay out, or complete the trip."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super5@example.com', password='pass12345!')

    def test_superadmin_can_assign_a_driver_to_a_vehicle(self):
        driver = Driver.objects.create(full_name='Company Driver', is_active=True)
        vehicle = make_vehicle(price_per_day=Decimal('1000'))

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'driver': driver.id}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['driver'], driver.id)
        self.assertEqual(response.json()['driver_name'], driver.full_name)

        vehicle.refresh_from_db()
        self.assertEqual(vehicle.driver_id, driver.id)

    def test_a_vehicle_with_no_driver_reports_a_null_driver_name(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get(f'/api/admin/fleet/{vehicle.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()['driver'])
        self.assertIsNone(response.json()['driver_name'])

    def test_cannot_assign_a_suspended_driver(self):
        suspended_driver = Driver.objects.create(full_name='Suspended Driver', is_active=False)
        vehicle = make_vehicle(price_per_day=Decimal('1000'))

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'driver': suspended_driver.id}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_driver_can_be_cleared_back_to_none(self):
        driver = Driver.objects.create(full_name='Removable Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/fleet/{vehicle.id}/', {'driver': ''}, format='multipart')
        self.assertEqual(response.status_code, 200)
        vehicle.refresh_from_db()
        self.assertIsNone(vehicle.driver_id)


class AdminBookingEditTests(APITestCase):
    """Admin needs a way to fix a booking assigned to the wrong driver (e.g. one created before
    its vehicle had a driver set) - a status change alone can't do that."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super7@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff7@example.com', password='pass12345!', is_staff=True)
        self.customer = User.objects.create_user(username='edit-client@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.booking = make_booking(self.customer, self.vehicle, status=BookingStatus.PENDING)

    def test_superadmin_can_reassign_the_driver(self):
        driver = Driver.objects.create(full_name='Reassigned Driver', is_active=True)
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/bookings/{self.booking.id}/', {'driver': driver.id}, format='json')
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.driver_id, driver.id)

    def test_support_staff_cannot_edit_a_booking(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(f'/api/admin/bookings/{self.booking.id}/', {'notes': 'Changed'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_support_staff_can_still_change_status(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/set-status/', {'status': 'confirmed'})
        self.assertEqual(response.status_code, 200)


class AdminBookingBalanceReminderTests(APITestCase):
    """Staff can nudge the assigned driver that a booking still has an outstanding balance -
    distinct from PaymentViewSet.remind (payments app), which is about a specific already-declared
    payment sitting unconfirmed. This works even if nothing has been declared yet."""

    def setUp(self):
        self.staff = User.objects.create_user(username='balance-staff@example.com', password='pass12345!', is_staff=True)
        self.superadmin = User.objects.create_superuser(username='balance-super@example.com', password='pass12345!')
        self.plain_user = User.objects.create_user(username='balance-plain@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Balance Driver', is_active=True, email='balance-driver@example.com')
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='balance-customer@example.com', password='pass12345!')
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING)

    def _url(self, booking=None):
        return f'/api/admin/bookings/{(booking or self.booking).id}/remind_balance/'

    def test_staff_can_remind_driver_of_outstanding_balance(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.booking.last_balance_reminder_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('balance-driver@example.com', mail.outbox[0].to)

    def test_superadmin_can_also_remind(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_cannot_remind_a_booking_with_no_outstanding_balance(self):
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.SUCCESSFUL,
        )
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_cannot_remind_a_booking_with_no_driver(self):
        other_vehicle = make_vehicle(name='No Driver Car', price_per_day=Decimal('1000'))
        other_booking = make_booking(self.customer, other_vehicle, status=BookingStatus.PENDING)
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url(other_booking))
        self.assertEqual(response.status_code, 400)

    def test_cannot_remind_a_cancelled_booking(self):
        self.booking.status = BookingStatus.CANCELLED
        self.booking.save(update_fields=['status'])
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 400)

    def test_cooldown_blocks_an_immediate_second_reminder(self):
        self.client.force_authenticate(user=self.staff)
        first = self.client.post(self._url())
        self.assertEqual(first.status_code, 200)
        second = self.client.post(self._url())
        self.assertEqual(second.status_code, 400)
        self.assertEqual(len(mail.outbox), 1)

    def test_non_staff_cannot_remind(self):
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 403)


class AdminSetStatusTripLifecycleTests(APITestCase):
    """set-status used to assign status directly, bypassing the same trip_started_at/
    trip_ended_at trail the driver portal's Start Trip/End Trip actions leave - an admin-driven
    transition left no record of whether the trip actually happened, and silently broke the
    late-payment auto-complete safety net (which depends on trip_ended_at already being set)."""

    def setUp(self):
        self.staff = User.objects.create_user(username='status-staff@example.com', password='pass12345!', is_staff=True)
        self.customer = User.objects.create_user(username='status-client@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.booking = make_booking(
            self.customer, self.vehicle, status=BookingStatus.CONFIRMED, customer_email='status-client@example.com',
        )
        self.client.force_authenticate(user=self.staff)

    def test_setting_ongoing_stamps_trip_started_at(self):
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/set-status/', {'status': 'ongoing'})
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.ONGOING)
        self.assertIsNotNone(self.booking.trip_started_at)

    def test_setting_completed_stamps_trip_ended_at_and_emails(self):
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        mail.outbox = []
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/set-status/', {'status': 'completed'})
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.COMPLETED)
        self.assertIsNotNone(self.booking.trip_ended_at)
        self.assertTrue(any('How was your ride' in m.subject for m in mail.outbox))

    def test_cannot_skip_straight_from_pending_to_ongoing(self):
        self.booking.status = BookingStatus.PENDING
        self.booking.save(update_fields=['status'])
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/set-status/', {'status': 'ongoing'})
        self.assertEqual(response.status_code, 400)

    def test_cannot_skip_straight_from_pending_to_completed_even_with_zero_balance(self):
        self.booking.status = BookingStatus.PENDING
        self.booking.save(update_fields=['status'])
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/set-status/', {'status': 'completed'})
        self.assertEqual(response.status_code, 400)

    def test_cannot_complete_with_undeposited_cash(self):
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/set-status/', {'status': 'completed'})
        self.assertEqual(response.status_code, 400)
        self.booking.refresh_from_db()
        self.assertNotEqual(self.booking.status, BookingStatus.COMPLETED)


class GovernmentContractBookingTests(APITestCase):
    """A government contract is confirmed with no deposit and paid for later via invoice,
    rather than upfront like an ordinary customer - see Booking.is_government_contract."""

    def setUp(self):
        self.staff = User.objects.create_user(username='gov-staff@example.com', password='pass12345!', is_staff=True)
        self.plain_user = User.objects.create_user(username='gov-plain@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Gov Driver', is_active=True, email='gov-driver@example.com')
        self.vehicle = make_vehicle(name='Gov Car', price_per_day=Decimal('1000'), driver=self.driver)
        self.client.force_authenticate(user=self.staff)

    def _create_payload(self, **overrides):
        payload = {
            'vehicle': self.vehicle.id, 'driver': self.driver.id, 'customer_name': 'Ministry of Health',
            'customer_phone': '254711222333', 'customer_email': 'procurement@health.go.ke',
            'pickup_location': 'Kisumu CBD', 'start_date': str(TOMORROW), 'end_date': str(NEXT_WEEK),
            'government_contract_reference': 'Ministry of Health - LPO#4821',
        }
        payload.update(overrides)
        return payload

    def test_creating_a_government_booking_confirms_immediately_with_no_deposit(self):
        mail.outbox = []
        response = self.client.post('/api/admin/bookings/create-government/', self._create_payload())
        self.assertEqual(response.status_code, 201)
        booking_id = response.data['id']
        booking = Booking.objects.get(pk=booking_id)
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)
        self.assertTrue(booking.is_government_contract)
        self.assertEqual(booking.government_contract_reference, 'Ministry of Health - LPO#4821')
        self.assertEqual(booking.amount_paid, Decimal('0'))
        self.assertGreater(booking.balance_due, 0)
        self.assertTrue(any('Booking Confirmed' in m.subject for m in mail.outbox))
        self.assertTrue(any('procurement@health.go.ke' in m.to for m in mail.outbox))

    def test_creating_a_government_booking_notifies_the_assigned_driver(self):
        mail.outbox = []
        self.client.post('/api/admin/bookings/create-government/', self._create_payload())
        self.assertTrue(any('gov-driver@example.com' in m.to for m in mail.outbox))

    def test_plain_customer_cannot_create_a_government_booking(self):
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.post('/api/admin/bookings/create-government/', self._create_payload())
        self.assertEqual(response.status_code, 403)

    def test_missing_contract_reference_is_rejected(self):
        payload = self._create_payload()
        del payload['government_contract_reference']
        response = self.client.post('/api/admin/bookings/create-government/', payload)
        self.assertEqual(response.status_code, 400)

    def test_malformed_customer_phone_is_rejected(self):
        response = self.client.post(
            '/api/admin/bookings/create-government/', self._create_payload(customer_phone='0712345678'),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('customer_phone', response.json())

    def test_conflicting_dates_are_rejected(self):
        make_booking(
            self.plain_user, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            start_date=TOMORROW, end_date=NEXT_WEEK,
        )
        response = self.client.post('/api/admin/bookings/create-government/', self._create_payload())
        self.assertEqual(response.status_code, 400)

    def test_a_government_contract_trip_completes_despite_an_outstanding_balance(self):
        booking = make_booking(
            self.plain_user, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            is_government_contract=True, government_contract_reference='LPO#1',
        )
        response = self.client.post(f'/api/admin/bookings/{booking.id}/set-status/', {'status': 'ongoing'})
        self.assertEqual(response.status_code, 200)
        response = self.client.post(f'/api/admin/bookings/{booking.id}/set-status/', {'status': 'completed'})
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)
        self.assertGreater(booking.balance_due, 0)

    def test_completing_a_government_contract_queues_the_driver_payout_despite_the_balance(self):
        driver_owned_vehicle = make_vehicle(name='Gov Payout Car', price_per_day=Decimal('1000'), driver=self.driver)
        booking = make_booking(
            self.plain_user, driver_owned_vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            is_government_contract=True, government_contract_reference='LPO#2',
        )
        self.client.post(f'/api/admin/bookings/{booking.id}/set-status/', {'status': 'ongoing'})
        self.client.post(f'/api/admin/bookings/{booking.id}/set-status/', {'status': 'completed'})
        self.assertTrue(DriverPayout.objects.filter(booking=booking).exists())

    def test_a_normal_booking_still_cannot_complete_with_an_outstanding_balance(self):
        booking = make_booking(self.plain_user, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED)
        self.client.post(f'/api/admin/bookings/{booking.id}/set-status/', {'status': 'ongoing'})
        response = self.client.post(f'/api/admin/bookings/{booking.id}/set-status/', {'status': 'completed'})
        self.assertEqual(response.status_code, 400)

    def test_recording_an_invoice_payment_creates_a_successful_payment(self):
        booking = make_booking(
            self.plain_user, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            is_government_contract=True, government_contract_reference='LPO#3',
        )
        response = self.client.post(
            f'/api/admin/bookings/{booking.id}/record-invoice-payment/',
            {'amount': str(booking.total_amount), 'reference': 'Bank transfer - Treasury ref 55821'},
        )
        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(booking=booking)
        self.assertEqual(payment.method, PaymentMethod.INVOICE)
        self.assertEqual(payment.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(payment.amount, booking.total_amount)
        self.assertEqual(payment.note, 'Bank transfer - Treasury ref 55821')
        booking.refresh_from_db()
        self.assertEqual(booking.balance_due, Decimal('0.00'))

    def test_recording_an_invoice_payment_rejects_a_non_government_booking(self):
        booking = make_booking(self.plain_user, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED)
        response = self.client.post(
            f'/api/admin/bookings/{booking.id}/record-invoice-payment/', {'amount': '1000'},
        )
        self.assertEqual(response.status_code, 400)

    def test_recording_an_invoice_payment_requires_a_positive_amount(self):
        booking = make_booking(
            self.plain_user, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            is_government_contract=True, government_contract_reference='LPO#4',
        )
        response = self.client.post(
            f'/api/admin/bookings/{booking.id}/record-invoice-payment/', {'amount': '0'},
        )
        self.assertEqual(response.status_code, 400)

    def test_non_staff_cannot_record_an_invoice_payment(self):
        booking = make_booking(
            self.plain_user, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            is_government_contract=True, government_contract_reference='LPO#5',
        )
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.post(
            f'/api/admin/bookings/{booking.id}/record-invoice-payment/', {'amount': '1000'},
        )
        self.assertEqual(response.status_code, 403)


class AdminConditionReportActionTests(APITestCase):
    """Staff-side equivalent of the driver portal's own condition-report action - covers a
    booking with no driver present to log one themselves (self-drive, or a company-owned
    vehicle's admin-driven trip). See bookings.views.DriverConditionReportView for the
    driver-facing counterpart."""

    def setUp(self):
        self.staff = User.objects.create_user(username='cond-staff@example.com', password='pass12345!', is_staff=True)
        self.plain_user = User.objects.create_user(username='cond-plain@example.com', password='pass12345!')
        self.vehicle = make_vehicle(name='Condition Car', price_per_day=Decimal('1000'))
        self.booking = make_booking(self.plain_user, self.vehicle, status=BookingStatus.CONFIRMED)
        self.client.force_authenticate(user=self.staff)

    def test_staff_can_log_a_condition_report(self):
        response = self.client.post(
            f'/api/admin/bookings/{self.booking.id}/condition-reports/',
            {'report_type': 'return', 'mileage': '50000', 'fuel_level': 'half'},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['report_type'], 'return')
        self.assertIsNone(data['logged_by_name'])

    def test_staff_can_list_condition_reports(self):
        self.client.post(f'/api/admin/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        response = self.client.get(f'/api/admin/bookings/{self.booking.id}/condition-reports/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_a_second_report_of_the_same_type_is_rejected(self):
        self.client.post(f'/api/admin/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        self.assertEqual(response.status_code, 400)

    def test_non_staff_cannot_log_a_condition_report(self):
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        self.assertEqual(response.status_code, 403)

    def test_org_admin_cannot_reach_another_orgs_booking(self):
        org = FleetPartner.objects.create(name='Condition Org', platform_fee_percent=Decimal('10'))
        org_admin = User.objects.create_user(
            username='cond-org-admin@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=org_admin, organization=org)
        self.client.force_authenticate(user=org_admin)

        response = self.client.post(f'/api/admin/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        self.assertEqual(response.status_code, 404)


class AdminVehicleGalleryTests(APITestCase):
    """A company-created vehicle previously had no way to get more than its single cover photo -
    only a driver's own submission required (and got) a real photo gallery."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super8@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff8@example.com', password='pass12345!', is_staff=True)
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))

    def _image(self, name='photo.jpg'):
        return SimpleUploadedFile(name, b'fake-image-bytes', content_type='image/jpeg')

    def test_superadmin_can_add_gallery_images(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(
            f'/api/admin/fleet/{self.vehicle.id}/gallery/',
            {'images': [self._image('a.jpg'), self._image('b.jpg')]}, format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()), 2)
        self.assertEqual(VehicleImage.objects.filter(vehicle=self.vehicle).count(), 2)

    def test_support_staff_cannot_add_gallery_images(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            f'/api/admin/fleet/{self.vehicle.id}/gallery/', {'images': [self._image()]}, format='multipart',
        )
        self.assertEqual(response.status_code, 403)

    def test_adding_with_no_images_is_rejected(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/admin/fleet/{self.vehicle.id}/gallery/', {}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_superadmin_can_remove_a_gallery_image(self):
        image = VehicleImage.objects.create(vehicle=self.vehicle, image=self._image())
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet/{self.vehicle.id}/gallery/{image.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(VehicleImage.objects.filter(id=image.id).exists())

    def test_cannot_remove_a_gallery_image_belonging_to_another_vehicle(self):
        other_vehicle = make_vehicle(name='Other Car', price_per_day=Decimal('1000'))
        image = VehicleImage.objects.create(vehicle=other_vehicle, image=self._image())
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet/{self.vehicle.id}/gallery/{image.id}/')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(VehicleImage.objects.filter(id=image.id).exists())


class AdminVehicleServiceRecordTests(APITestCase):
    """Company-owned vehicles have no owning driver-partner to log a service themselves, so
    admin needs a way to log one directly - same superadmin tier as other vehicle-data changes
    (gallery images, category)."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super10@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff10@example.com', password='pass12345!', is_staff=True)
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))

    def test_superadmin_can_log_a_service_record(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(
            f'/api/admin/fleet/{self.vehicle.id}/service-records/',
            {'service_date': '2026-01-15', 'notes': 'General service'}, format='json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(VehicleServiceRecord.objects.filter(vehicle=self.vehicle).count(), 1)
        self.assertTrue(AuditLog.objects.filter(action='vehicle.add_service_record').exists())

    def test_support_staff_cannot_log_a_service_record(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            f'/api/admin/fleet/{self.vehicle.id}/service-records/',
            {'service_date': '2026-01-15', 'notes': 'General service'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(VehicleServiceRecord.objects.exists())

    def test_service_records_are_nested_on_the_admin_vehicle_detail(self):
        VehicleServiceRecord.objects.create(vehicle=self.vehicle, service_date='2026-01-15', notes='Oil change')
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(f'/api/admin/fleet/{self.vehicle.id}/')
        self.assertEqual(response.json()['service_records'][0]['notes'], 'Oil change')

    def test_is_service_due_is_exposed_on_the_admin_vehicle_detail(self):
        old_created_at = timezone.now() - timedelta(days=Vehicle.SERVICE_DUE_INTERVAL_DAYS + 1)
        Vehicle.objects.filter(pk=self.vehicle.pk).update(created_at=old_created_at)
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(f'/api/admin/fleet/{self.vehicle.id}/')
        self.assertTrue(response.json()['is_service_due'])

        VehicleServiceRecord.objects.create(vehicle=self.vehicle, service_date=timezone.now().date())
        response = self.client.get(f'/api/admin/fleet/{self.vehicle.id}/')
        self.assertFalse(response.json()['is_service_due'])


class AdminStatsServiceDueTests(APITestCase):
    """The dashboard's Fleet section surfaces how many vehicles are overdue for service, same
    tier (any staff can view) as the other "needs attention" stats."""

    def setUp(self):
        self.staff = User.objects.create_user(username='staff-stats-service@example.com', password='pass12345!', is_staff=True)

    def test_stats_counts_vehicles_overdue_for_service(self):
        due_vehicle = make_vehicle(price_per_day=Decimal('1000'))
        old_created_at = timezone.now() - timedelta(days=Vehicle.SERVICE_DUE_INTERVAL_DAYS + 1)
        Vehicle.objects.filter(pk=due_vehicle.pk).update(created_at=old_created_at)

        not_due_vehicle = make_vehicle(price_per_day=Decimal('1000'))
        VehicleServiceRecord.objects.create(vehicle=not_due_vehicle, service_date=timezone.now().date())

        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['fleet']['service_due'], 1)


class AdminStatsFleetPartnerTests(APITestCase):
    """The dashboard's per-partner breakdown (bookings, revenue, fee owed on their vehicles) is
    superadmin-only, like everything else about a FleetPartner."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super-stats-partner@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff-stats-partner@example.com', password='pass12345!', is_staff=True)
        self.partner = FleetPartner.objects.create(name='Stats Partner Co', platform_fee_percent=Decimal('10'))
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'), owner=self.partner, is_company_owned=False)
        self.customer = User.objects.create_user(username='stats-partner-client@example.com', password='pass12345!')

    def test_support_staff_does_not_see_fleet_partner_breakdown(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['fleet_partners'], [])

    def test_superadmin_sees_fleet_partner_breakdown(self):
        booking = make_booking(self.customer, self.vehicle, status=BookingStatus.PENDING)
        Payment.objects.create(booking=booking, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL)
        booking.confirm_if_deposit_met()  # triggers the real DriverPayout(organization=partner)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, 200)
        partners = response.json()['fleet_partners']
        self.assertEqual(len(partners), 1)
        entry = partners[0]
        self.assertEqual(entry['name'], 'Stats Partner Co')
        self.assertEqual(entry['vehicle_count'], 1)
        self.assertEqual(entry['bookings_count'], 1)
        self.assertEqual(Decimal(str(entry['total_revenue'])), booking.total_amount)
        self.assertEqual(Decimal(str(entry['total_collected'])), booking.total_amount)
        expected_fee = (booking.total_amount * Decimal('10') / Decimal('100')).quantize(Decimal('0.01'))
        self.assertEqual(Decimal(str(entry['platform_fee_earned'])), expected_fee)
        self.assertEqual(Decimal(str(entry['payout_owed'])), booking.total_amount - expected_fee)
        self.assertEqual(Decimal(str(entry['payout_paid'])), 0)

    def test_cancelled_bookings_are_excluded_from_partner_totals(self):
        booking = make_booking(self.customer, self.vehicle, status=BookingStatus.CANCELLED)
        Payment.objects.create(booking=booking, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL)

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get('/api/admin/stats/')
        entry = response.json()['fleet_partners'][0]
        self.assertEqual(entry['bookings_count'], 0)
        self.assertEqual(Decimal(str(entry['total_revenue'])), 0)
        self.assertEqual(Decimal(str(entry['total_collected'])), 0)

    def test_inactive_partner_is_excluded(self):
        self.partner.is_active = False
        self.partner.save(update_fields=['is_active'])
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.json()['fleet_partners'], [])


class AdminAnalyticsViewTests(APITestCase):
    """Revenue trend, top vehicles, and new-vs-repeat customers over the trailing 12 calendar
    months - the "how's the business doing" picture AdminStatsView's snapshot doesn't cover."""

    def setUp(self):
        self.staff = User.objects.create_user(username='staff-analytics@example.com', password='pass12345!', is_staff=True)
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='analytics-client@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.staff)

    def test_anonymous_cannot_view_analytics(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/admin/analytics/')
        self.assertIn(response.status_code, (401, 403))

    def test_response_shape(self):
        response = self.client.get('/api/admin/analytics/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['window_months'], 12)
        self.assertEqual(len(data['revenue_trend']), 12)
        self.assertIn('top_vehicles', data)
        self.assertIn('new', data['customers'])
        self.assertIn('repeat', data['customers'])
        self.assertIn('repeat_rate', data['customers'])

    def test_revenue_trend_zero_fills_months_with_no_activity(self):
        response = self.client.get('/api/admin/analytics/')
        self.assertTrue(all(month['revenue'] == 0 for month in response.json()['revenue_trend']))

    def test_revenue_trend_includes_a_payment_made_this_month(self):
        booking = make_booking(self.customer, self.vehicle, status=BookingStatus.CONFIRMED)
        Payment.objects.create(booking=booking, amount=Decimal('5000'), status=PaymentStatus.SUCCESSFUL)

        response = self.client.get('/api/admin/analytics/')
        current_month_total = response.json()['revenue_trend'][-1]['revenue']
        self.assertEqual(Decimal(str(current_month_total)), Decimal('5000'))

    def test_revenue_trend_excludes_payments_older_than_the_window(self):
        booking = make_booking(self.customer, self.vehicle, status=BookingStatus.CONFIRMED)
        payment = Payment.objects.create(booking=booking, amount=Decimal('5000'), status=PaymentStatus.SUCCESSFUL)
        old_date = timezone.now() - timedelta(days=400)
        Payment.objects.filter(pk=payment.pk).update(created_at=old_date)

        response = self.client.get('/api/admin/analytics/')
        self.assertTrue(all(month['revenue'] == 0 for month in response.json()['revenue_trend']))

    def test_revenue_trend_excludes_unsuccessful_payments(self):
        booking = make_booking(self.customer, self.vehicle, status=BookingStatus.PENDING)
        Payment.objects.create(booking=booking, amount=Decimal('5000'), status=PaymentStatus.PENDING)

        response = self.client.get('/api/admin/analytics/')
        self.assertTrue(all(month['revenue'] == 0 for month in response.json()['revenue_trend']))

    def test_top_vehicles_are_ranked_by_revenue(self):
        big_vehicle = make_vehicle(name='Big Earner', price_per_day=Decimal('1000'))
        small_vehicle = make_vehicle(name='Small Earner', price_per_day=Decimal('1000'))
        big_booking = make_booking(self.customer, big_vehicle, status=BookingStatus.CONFIRMED)
        Payment.objects.create(booking=big_booking, amount=Decimal('9000'), status=PaymentStatus.SUCCESSFUL)
        small_booking = make_booking(self.customer, small_vehicle, status=BookingStatus.CONFIRMED)
        Payment.objects.create(booking=small_booking, amount=Decimal('1000'), status=PaymentStatus.SUCCESSFUL)

        response = self.client.get('/api/admin/analytics/')
        names = [row['name'] for row in response.json()['top_vehicles']]
        self.assertEqual(names[:2], ['Big Earner', 'Small Earner'])

    def test_pending_bookings_dont_count_toward_top_vehicles(self):
        make_booking(self.customer, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.get('/api/admin/analytics/')
        self.assertEqual(response.json()['top_vehicles'], [])

    def test_cancelled_bookings_dont_count_toward_top_vehicles(self):
        booking = make_booking(self.customer, self.vehicle, status=BookingStatus.CANCELLED)
        Payment.objects.create(booking=booking, amount=Decimal('5000'), status=PaymentStatus.SUCCESSFUL)
        response = self.client.get('/api/admin/analytics/')
        self.assertEqual(response.json()['top_vehicles'], [])

    def test_a_customers_first_ever_booking_counts_as_new(self):
        make_booking(self.customer, self.vehicle, status=BookingStatus.CONFIRMED)
        response = self.client.get('/api/admin/analytics/')
        customers = response.json()['customers']
        self.assertEqual(customers['new'], 1)
        self.assertEqual(customers['repeat'], 0)

    def test_a_customer_with_a_booking_before_the_window_counts_as_repeat(self):
        old_booking = make_booking(self.customer, self.vehicle, status=BookingStatus.CONFIRMED)
        Booking.objects.filter(pk=old_booking.pk).update(created_at=timezone.now() - timedelta(days=400))
        make_booking(self.customer, self.vehicle, status=BookingStatus.CONFIRMED, start_date=TOMORROW + timedelta(days=60), end_date=NEXT_WEEK + timedelta(days=60))

        response = self.client.get('/api/admin/analytics/')
        customers = response.json()['customers']
        self.assertEqual(customers['new'], 0)
        self.assertEqual(customers['repeat'], 1)
        self.assertEqual(customers['repeat_rate'], 100.0)

    def test_a_pending_booking_doesnt_count_as_customer_activity(self):
        make_booking(self.customer, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.get('/api/admin/analytics/')
        customers = response.json()['customers']
        self.assertEqual(customers['new'], 0)
        self.assertEqual(customers['repeat'], 0)
        self.assertEqual(customers['repeat_rate'], 0)

    def test_org_admin_only_sees_their_own_organizations_data(self):
        org = FleetPartner.objects.create(name='Analytics Org', platform_fee_percent=Decimal('10'))
        org_admin = User.objects.create_user(
            username='org-admin-analytics@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=org_admin, organization=org)

        other_orgs_booking = make_booking(self.customer, self.vehicle, status=BookingStatus.CONFIRMED)
        Payment.objects.create(booking=other_orgs_booking, amount=Decimal('9000'), status=PaymentStatus.SUCCESSFUL)

        self.client.force_authenticate(user=org_admin)
        response = self.client.get('/api/admin/analytics/')
        data = response.json()
        self.assertEqual(data['top_vehicles'], [])
        self.assertTrue(all(month['revenue'] == 0 for month in data['revenue_trend']))
        self.assertEqual(data['customers']['new'], 0)


class AdminVehicleCategoryTests(APITestCase):
    """Fleet types used to be a fixed enum in code - now a plain admin-editable list.
    Create/update/delete are superadmin-only (fleet composition tier); support staff can
    still list them to populate forms. Deleting one still referenced by a vehicle,
    submission, or driver application must be blocked, not silently orphan those records."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super9@example.com', password='pass12345!')
        self.staff = User.objects.create_user(username='staff9@example.com', password='pass12345!', is_staff=True)

    def test_anyone_authenticated_as_staff_can_list_categories(self):
        VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/fleet-types/')
        self.assertEqual(response.status_code, 200)
        names = [c['name'] for c in response.json().get('results', response.json())]
        self.assertIn('Luxury Convertible', names)

    def test_superadmin_can_create_a_category_with_an_auto_generated_slug(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post('/api/admin/fleet-types/', {'name': 'Luxury Convertible', 'order': 5})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['slug'], 'luxury-convertible')
        self.assertTrue(VehicleCategory.objects.filter(slug='luxury-convertible').exists())

    def test_superadmin_can_retire_a_category_without_deleting_it(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(f'/api/admin/fleet-types/{category.id}/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertFalse(category.is_active)
        # Still visible on the admin dashboard, just no longer publicly offered.
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_support_staff_cannot_retire_a_category(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.staff)
        response = self.client.patch(f'/api/admin/fleet-types/{category.id}/', {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 403)
        category.refresh_from_db()
        self.assertTrue(category.is_active)

    def test_support_staff_cannot_create_a_category(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post('/api/admin/fleet-types/', {'name': 'Luxury Convertible'})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(VehicleCategory.objects.filter(name='Luxury Convertible').exists())

    def test_support_staff_cannot_delete_a_category(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.staff)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_superadmin_can_delete_an_unused_category(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(VehicleCategory.objects.filter(id=category.id).exists())

    def test_deleting_a_category_still_used_by_a_vehicle_is_blocked(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        make_vehicle(category=category, price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_deleting_a_category_still_used_by_a_vehicle_submission_is_blocked(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        driver = Driver.objects.create(full_name='Submitting Driver', is_active=True)
        VehicleSubmission.objects.create(
            driver=driver, name='Submitted Car', category=category,
            passenger_capacity=4, price_per_day=5000,
            logbook_document=SimpleUploadedFile('logbook.pdf', b'x', content_type='application/pdf'),
        )
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_deleting_a_category_still_used_by_a_driver_application_is_blocked(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        DriverApplication.objects.create(
            full_name='Applicant', email='applicant@example.com', phone_number='254700000000',
            license_number='DL1', license_document=SimpleUploadedFile('l.jpg', b'x', content_type='image/jpeg'),
            vehicle_name='Convertible One', vehicle_category=category,
            passenger_capacity=2, price_per_day=8000,
        )
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(VehicleCategory.objects.filter(id=category.id).exists())

    def test_deleting_a_category_is_logged(self):
        category = VehicleCategory.objects.create(name='Luxury Convertible')
        self.client.force_authenticate(user=self.superadmin)
        self.client.delete(f'/api/admin/fleet-types/{category.id}/')
        self.assertTrue(AuditLog.objects.filter(action='vehicle_category.delete').exists())


class BrandedEmailTests(TestCase):
    """Every branded email embeds the logo inline via Content-ID rather than a remote URL, so
    it always renders regardless of the recipient's client blocking remote images. A previous
    Django upgrade silently broke this (an attribute it relied on was removed) - every branded
    send failed and got swallowed by the caller's try/except, so nothing surfaced until this
    test was added to catch it directly."""

    def test_branded_email_embeds_the_logo_inline(self):
        from core.email_utils import send_branded_email

        mail.outbox = []
        send_branded_email(
            subject='Test',
            template_name='emails/trip_completed.html',
            context={'first_name': 'Jane', 'vehicle_name': 'Test Car', 'review_url': 'http://example.com'},
            recipient_list=['jane@example.com'],
        )
        self.assertEqual(len(mail.outbox), 1)
        raw = mail.outbox[0].message().as_string()
        self.assertIn('cid:logo', raw)
        self.assertIn('Content-ID: <logo>', raw)


class ReplacedFileCleanupTests(APITestCase):
    """Reassigning a FileField/ImageField and saving doesn't make Django delete whatever file
    used to be there - without an explicit cleanup, replacing a vehicle photo/insurance document
    or a driver photo via the admin orphans the old file in storage forever (see
    core.utils.capture_replaced_files/delete_files, and the same fix on the customer-facing
    booking update endpoint for license/ID documents)."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='super-cleanup@example.com', password='pass12345!')

    def _png(self, name):
        import base64
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        return SimpleUploadedFile(name, png, content_type='image/png')

    def test_replacing_a_vehicle_image_deletes_the_old_file(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))
        vehicle.image.save('first.png', self._png('first.png'), save=True)
        old_name = vehicle.image.name
        self.assertTrue(vehicle.image.storage.exists(old_name))

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(
            f'/api/admin/fleet/{vehicle.id}/', {'image': self._png('second.png')}, format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        vehicle.refresh_from_db()
        self.assertNotEqual(vehicle.image.name, old_name)
        self.assertFalse(vehicle.image.storage.exists(old_name))

    def test_replacing_a_driver_photo_deletes_the_old_file(self):
        driver = Driver.objects.create(full_name='Cleanup Driver', is_active=True)
        driver.photo.save('first.png', self._png('first.png'), save=True)
        old_name = driver.photo.name
        self.assertTrue(driver.photo.storage.exists(old_name))

        self.client.force_authenticate(user=self.superadmin)
        response = self.client.patch(
            f'/api/admin/drivers/{driver.id}/', {'photo': self._png('second.png')}, format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        driver.refresh_from_db()
        self.assertNotEqual(driver.photo.name, old_name)
        self.assertFalse(driver.photo.storage.exists(old_name))


class OrganizationScopingTests(APITestCase):
    """A FleetPartner's own org-admin (is_staff=True, is_superuser=True, with a
    StaffOrganization pointing at their org) gets the same tier of action a real SilverLake
    superadmin does, but strictly scoped to their own organization's data - never another
    org's, never SilverLake's own platform-only resources."""

    def setUp(self):
        self.platform_super = User.objects.create_superuser(username='platform-super@example.com', password='pass12345!')

        self.org_a = FleetPartner.objects.create(name='Org A', platform_fee_percent=Decimal('10'))
        self.org_b = FleetPartner.objects.create(name='Org B', platform_fee_percent=Decimal('10'))

        self.org_a_admin = User.objects.create_user(
            username='org-a-admin@example.com', email='org-a-admin@example.com',
            password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=self.org_a_admin, organization=self.org_a)

        self.org_a_driver = Driver.objects.create(full_name='Org A Driver', is_active=True)
        self.org_a_vehicle = make_vehicle(
            name='Org A Car', price_per_day=Decimal('1000'),
            owner=self.org_a, is_company_owned=False, driver=self.org_a_driver,
        )

        self.org_b_admin = User.objects.create_user(
            username='org-b-admin@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=self.org_b_admin, organization=self.org_b)
        self.org_b_vehicle = make_vehicle(
            name='Org B Car', price_per_day=Decimal('1000'), owner=self.org_b, is_company_owned=False,
        )

        self.customer = User.objects.create_user(username='scoping-customer@example.com', password='pass12345!')
        self.org_a_booking = make_booking(
            self.customer, self.org_a_vehicle, driver=self.org_a_driver, status=BookingStatus.PENDING,
        )
        self.org_b_booking = make_booking(self.customer, self.org_b_vehicle, status=BookingStatus.PENDING)

    # ── Fleet ────────────────────────────────────────────────────────────────
    def test_org_admin_only_sees_their_own_vehicles(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/fleet/')
        names = [v['name'] for v in response.json().get('results', response.json())]
        self.assertEqual(names, ['Org A Car'])

    def test_org_admin_creating_a_vehicle_is_forced_into_their_own_org(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.post('/api/admin/fleet/', {
            'name': 'New Org A Car', 'category': 'compact_sedan', 'passenger_capacity': 4,
            'price_per_day': '2000', 'owner': self.org_b.id, 'is_company_owned': True,
        }, format='multipart')
        self.assertEqual(response.status_code, 201)
        vehicle = Vehicle.objects.get(name='New Org A Car')
        self.assertEqual(vehicle.owner_id, self.org_a.id)
        self.assertFalse(vehicle.is_company_owned)

    def test_org_admin_cannot_reach_another_orgs_vehicle(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get(f'/api/admin/fleet/{self.org_b_vehicle.id}/')
        self.assertEqual(response.status_code, 404)

    # ── Bookings / Payments / Payouts / Refunds ─────────────────────────────
    def test_org_admin_only_sees_their_own_bookings(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/bookings/')
        ids = [b['id'] for b in response.json().get('results', response.json())]
        self.assertEqual(ids, [self.org_a_booking.id])

    def test_org_admin_cannot_reach_another_orgs_booking(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get(f'/api/admin/bookings/{self.org_b_booking.id}/')
        self.assertEqual(response.status_code, 404)

    def test_general_booking_endpoint_is_also_org_scoped_for_staff(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/bookings/')
        ids = [b['id'] for b in response.json().get('results', response.json())]
        self.assertEqual(ids, [self.org_a_booking.id])

    def test_org_admin_only_sees_payments_on_their_own_bookings(self):
        Payment.objects.create(booking=self.org_a_booking, method=PaymentMethod.MPESA, amount=Decimal('100'), status=PaymentStatus.SUCCESSFUL)
        Payment.objects.create(booking=self.org_b_booking, method=PaymentMethod.MPESA, amount=Decimal('100'), status=PaymentStatus.SUCCESSFUL)
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/payments/')
        bookings_seen = {p['booking'] for p in response.json().get('results', response.json())}
        self.assertEqual(bookings_seen, {self.org_a_booking.id})

    def test_org_admin_only_sees_their_own_refunds(self):
        Refund.objects.create(booking=self.org_a_booking, amount=Decimal('100'))
        Refund.objects.create(booking=self.org_b_booking, amount=Decimal('100'))
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/refunds/')
        booking_ids = [r['booking_id'] for r in response.json().get('results', response.json())]
        self.assertEqual(booking_ids, [self.org_a_booking.id])

    # ── Platform-only resources ──────────────────────────────────────────────
    def test_org_admin_cannot_view_fleet_partners(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/fleet-partners/')
        self.assertEqual(response.status_code, 403)

    def test_org_admin_cannot_change_their_own_platform_fee(self):
        # Only a genuine SilverLake superadmin can ever touch platform_fee_percent - not even an
        # org-admin editing their own organization's record.
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.patch(
            f'/api/admin/fleet-partners/{self.org_a.id}/', {'platform_fee_percent': '0'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.org_a.refresh_from_db()
        self.assertEqual(self.org_a.platform_fee_percent, Decimal('10'))

    def test_org_admin_cannot_create_a_fleet_type(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.post('/api/admin/fleet-types/', {'name': 'Rogue Type'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_org_admin_can_still_read_fleet_types(self):
        VehicleCategory.objects.create(name='Shared Type')
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/fleet-types/')
        self.assertEqual(response.status_code, 200)

    def test_org_admin_cannot_view_driver_applications(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/driver-applications/')
        self.assertEqual(response.status_code, 403)

    def test_org_admin_cannot_view_vehicle_submissions(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/vehicle-submissions/')
        self.assertEqual(response.status_code, 403)

    def test_org_admin_only_sees_their_own_orgs_audit_log_entries(self):
        # Reassigning each booking's driver logs 'booking.update' with the organization
        # inferred from booking.vehicle.owner (see core.audit._infer_organization).
        self.client.force_authenticate(user=self.platform_super)
        self.client.patch(f'/api/admin/bookings/{self.org_a_booking.id}/', {'driver': self.org_a_driver.id}, format='json')
        self.client.patch(f'/api/admin/bookings/{self.org_b_booking.id}/', {'driver': self.org_a_driver.id}, format='json')

        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/audit-log/')
        self.assertEqual(response.status_code, 200)
        entries = response.json().get('results', response.json())
        self.assertTrue(entries)
        self.assertTrue(all(entry['organization_name'] == 'Org A' for entry in entries))

    def test_org_admin_cannot_see_platform_only_audit_log_entries(self):
        driver = Driver.objects.create(full_name='Platform-Only Driver', is_active=True)
        self.client.force_authenticate(user=self.platform_super)
        self.client.post(f'/api/admin/drivers/{driver.id}/suspend/', {'reason': 'test'})

        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/audit-log/')
        actions = [entry['action'] for entry in response.json().get('results', response.json())]
        self.assertNotIn('driver.suspend', actions)

    def test_platform_superadmin_still_has_full_access_to_platform_only_resources(self):
        self.client.force_authenticate(user=self.platform_super)
        self.assertEqual(self.client.get('/api/admin/fleet-partners/').status_code, 200)
        self.assertEqual(self.client.get('/api/admin/driver-applications/').status_code, 200)
        self.assertEqual(self.client.get('/api/admin/audit-log/').status_code, 200)

    # ── Stats ────────────────────────────────────────────────────────────────
    def test_org_admin_stats_are_scoped_to_their_own_org(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['bookings']['total'], 1)
        self.assertEqual(data['fleet']['total'], 1)
        self.assertEqual(data['fleet_partners'], [])

    def test_platform_superadmin_stats_include_all_orgs_fleet_partner_breakdown(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.get('/api/admin/stats/')
        data = response.json()
        self.assertEqual(data['bookings']['total'], 2)
        names = {p['name'] for p in data['fleet_partners']}
        self.assertEqual(names, {'Org A', 'Org B'})

    # ── Staff/users ──────────────────────────────────────────────────────────
    def test_org_admin_only_sees_their_own_orgs_staff(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/users/')
        emails = [u['email'] for u in response.json().get('results', response.json())]
        self.assertEqual(emails, ['org-a-admin@example.com'])

    def test_org_admin_invites_staff_into_their_own_org_only(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.post('/api/admin/users/invite-staff/', {
            'email': 'new-org-a-staff@example.com', 'first_name': 'New', 'last_name': 'Staffer',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        new_user = User.objects.get(username='new-org-a-staff@example.com')
        self.assertTrue(new_user.is_staff)
        self.assertEqual(new_user.staff_organization.organization_id, self.org_a.id)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('new-org-a-staff@example.com', mail.outbox[0].to)

    def test_platform_superadmin_invited_staff_has_no_organization(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post('/api/admin/users/invite-staff/', {
            'email': 'new-platform-staff@example.com',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        new_user = User.objects.get(username='new-platform-staff@example.com')
        self.assertFalse(hasattr(new_user, 'staff_organization'))

    def test_non_superadmin_cannot_invite_staff(self):
        staff = User.objects.create_user(username='plain-staff@example.com', password='pass12345!', is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.post('/api/admin/users/invite-staff/', {'email': 'x@example.com'}, format='json')
        self.assertEqual(response.status_code, 403)

    # ── FleetPartner registration auto-invite ───────────────────────────────
    def test_registering_a_partner_with_contact_email_sends_an_invite(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post('/api/admin/fleet-partners/', {
            'name': 'Invited Co', 'contact_email': 'admin@invitedco.co.ke',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        new_user = User.objects.get(username='admin@invitedco.co.ke')
        self.assertTrue(new_user.is_staff)
        self.assertTrue(new_user.is_superuser)
        partner = FleetPartner.objects.get(name='Invited Co')
        self.assertEqual(new_user.staff_organization.organization_id, partner.id)
        self.assertEqual(len(mail.outbox), 1)

    def test_registering_a_partner_without_contact_email_sends_no_invite(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post('/api/admin/fleet-partners/', {'name': 'No Email Co'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)

    def test_invite_admin_action_sends_invite_after_the_fact(self):
        partner = FleetPartner.objects.create(name='Late Email Co', contact_email='late@lateco.co.ke')
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/fleet-partners/{partner.id}/invite-admin/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        new_user = User.objects.get(username='late@lateco.co.ke')
        self.assertEqual(new_user.staff_organization.organization_id, partner.id)

    def test_org_admin_cannot_invite_admin_for_a_partner(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.post(f'/api/admin/fleet-partners/{self.org_a.id}/invite-admin/')
        self.assertEqual(response.status_code, 403)

    def test_platform_superadmin_can_notify_a_specific_organization(self):
        from notifications.models import Notification, NotificationEvent

        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(
            f'/api/admin/fleet-partners/{self.org_a.id}/notify/', {'message': 'Please update your fleet photos.'},
        )
        self.assertEqual(response.status_code, 204)
        notification = Notification.objects.get(event=NotificationEvent.ADMIN_MESSAGE)
        self.assertEqual(notification.organization_id, self.org_a.id)
        self.assertEqual(notification.message, 'Please update your fleet photos.')

    def test_notifying_a_partner_only_reaches_that_orgs_own_admin(self):
        self.client.force_authenticate(user=self.platform_super)
        self.client.post(f'/api/admin/fleet-partners/{self.org_a.id}/notify/', {'message': 'For org A only.'})

        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.get('/api/admin/notifications/')
        messages = [n['message'] for n in response.json()['results']]
        self.assertIn('For org A only.', messages)

        self.client.force_authenticate(user=self.org_b_admin)
        response = self.client.get('/api/admin/notifications/')
        messages = [n['message'] for n in response.json()['results']]
        self.assertNotIn('For org A only.', messages)

    def test_notify_requires_a_message(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/fleet-partners/{self.org_a.id}/notify/', {})
        self.assertEqual(response.status_code, 400)

    def test_org_admin_cannot_notify_another_organization(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.post(f'/api/admin/fleet-partners/{self.org_b.id}/notify/', {'message': 'Trying anyway.'})
        self.assertEqual(response.status_code, 403)

    def test_notifying_logs_an_audit_entry(self):
        self.client.force_authenticate(user=self.platform_super)
        self.client.post(f'/api/admin/fleet-partners/{self.org_a.id}/notify/', {'message': 'Logged message.'})
        entry = AuditLog.objects.get(action='fleet_partner.notify')
        self.assertEqual(entry.detail, 'Logged message.')

    # ── Government contract bookings ────────────────────────────────────────
    def test_org_admin_cannot_create_a_government_booking_for_another_orgs_vehicle(self):
        # Dates offset well clear of org_b_booking's own TOMORROW-NEXT_WEEK range from setUp,
        # so this fails on the org-scoping check and nothing else.
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.post('/api/admin/bookings/create-government/', {
            'vehicle': self.org_b_vehicle.id, 'customer_name': 'Ministry Contact',
            'customer_phone': '254711000000', 'pickup_location': 'Kisumu',
            'start_date': str(TOMORROW + timedelta(days=30)), 'end_date': str(TOMORROW + timedelta(days=35)),
            'government_contract_reference': 'LPO#1',
        })
        self.assertEqual(response.status_code, 403)

    def test_org_admin_can_create_a_government_booking_for_their_own_vehicle(self):
        self.client.force_authenticate(user=self.org_a_admin)
        response = self.client.post('/api/admin/bookings/create-government/', {
            'vehicle': self.org_a_vehicle.id, 'customer_name': 'Ministry Contact',
            'customer_phone': '254711000001', 'pickup_location': 'Kisumu',
            'start_date': str(TOMORROW + timedelta(days=30)), 'end_date': str(TOMORROW + timedelta(days=35)),
            'government_contract_reference': 'LPO#2',
        })
        self.assertEqual(response.status_code, 201)


class AdminSearchAndFilterTests(APITestCase):
    """Every admin list view got a search box and a couple of filter dropdowns - a blank
    search/filter must always behave exactly like before (org-scoping tests above already cover
    that), so these only check that a non-blank value actually narrows the result set."""

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username='search-staff@example.com', email='search-staff@example.com', password='pass12345!',
        )
        self.client.force_authenticate(user=self.staff)

        self.customer = User.objects.create_user(
            username='alice@example.com', email='alice@example.com',
            first_name='Alice', last_name='Wonderland', password='pass12345!',
        )
        self.other_customer = User.objects.create_user(
            username='bob@example.com', email='bob@example.com',
            first_name='Bob', last_name='Builder', password='pass12345!',
        )

        self.driver = Driver.objects.create(full_name='Kip Keino', email='kip@example.com', phone_number='254711111111', is_active=True)
        self.other_driver = Driver.objects.create(full_name='Wanjiru Njoroge', is_active=True)

        self.vehicle = make_vehicle(name='Toyota Prado', price_per_day=Decimal('5000'))
        self.other_vehicle = make_vehicle(name='Nissan Note', price_per_day=Decimal('2000'))

        self.booking = make_booking(
            self.customer, self.vehicle, driver=self.driver,
            customer_name='Alice Wonderland', customer_phone='254700111222', customer_email='alice@example.com',
        )
        self.other_booking = make_booking(
            self.other_customer, self.other_vehicle,
            customer_name='Bob Builder', customer_phone='254700333444', customer_email='bob@example.com',
        )

    # ── Bookings ─────────────────────────────────────────────────────────────
    def test_booking_search_matches_customer_name(self):
        response = self.client.get('/api/admin/bookings/', {'search': 'Wonderland'})
        ids = [b['id'] for b in response.json().get('results', response.json())]
        self.assertEqual(ids, [self.booking.id])

    def test_booking_filter_by_status(self):
        self.other_booking.status = BookingStatus.CANCELLED
        self.other_booking.save(update_fields=['status'])
        response = self.client.get('/api/admin/bookings/', {'status': BookingStatus.CANCELLED})
        ids = [b['id'] for b in response.json().get('results', response.json())]
        self.assertEqual(ids, [self.other_booking.id])

    def test_booking_blank_search_returns_everything(self):
        response = self.client.get('/api/admin/bookings/', {'search': ''})
        ids = {b['id'] for b in response.json().get('results', response.json())}
        self.assertEqual(ids, {self.booking.id, self.other_booking.id})

    # ── Users ────────────────────────────────────────────────────────────────
    def test_user_search_matches_email(self):
        response = self.client.get('/api/admin/users/', {'search': 'alice@example.com'})
        emails = [u['email'] for u in response.json().get('results', response.json())]
        self.assertEqual(emails, ['alice@example.com'])

    def test_user_filter_by_role_superadmin(self):
        response = self.client.get('/api/admin/users/', {'role': 'superadmin'})
        emails = [u['email'] for u in response.json().get('results', response.json())]
        self.assertEqual(emails, ['search-staff@example.com'])

    def test_user_filter_by_role_customer(self):
        response = self.client.get('/api/admin/users/', {'role': 'customer'})
        emails = {u['email'] for u in response.json().get('results', response.json())}
        self.assertEqual(emails, {'alice@example.com', 'bob@example.com'})

    # ── Fleet ────────────────────────────────────────────────────────────────
    def test_fleet_search_matches_name(self):
        response = self.client.get('/api/admin/fleet/', {'search': 'Prado'})
        names = [v['name'] for v in response.json().get('results', response.json())]
        self.assertEqual(names, ['Toyota Prado'])

    def test_fleet_filter_by_availability(self):
        self.other_vehicle.is_available = False
        self.other_vehicle.save(update_fields=['is_available'])
        response = self.client.get('/api/admin/fleet/', {'is_available': 'false'})
        names = [v['name'] for v in response.json().get('results', response.json())]
        self.assertEqual(names, ['Nissan Note'])

    # ── Drivers ──────────────────────────────────────────────────────────────
    def test_driver_search_matches_name(self):
        response = self.client.get('/api/admin/drivers/', {'search': 'Keino'})
        names = [d['full_name'] for d in response.json().get('results', response.json())]
        self.assertEqual(names, ['Kip Keino'])

    def test_driver_search_matches_email(self):
        response = self.client.get('/api/admin/drivers/', {'search': 'kip@example.com'})
        names = [d['full_name'] for d in response.json().get('results', response.json())]
        self.assertEqual(names, ['Kip Keino'])

    # ── Payments ─────────────────────────────────────────────────────────────
    def test_payment_search_matches_mpesa_receipt(self):
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA, amount=Decimal('100'),
            status=PaymentStatus.SUCCESSFUL, mpesa_receipt_number='ABC123XYZ',
        )
        Payment.objects.create(
            booking=self.other_booking, method=PaymentMethod.MPESA, amount=Decimal('100'), status=PaymentStatus.SUCCESSFUL,
        )
        response = self.client.get('/api/payments/', {'search': 'ABC123XYZ'})
        receipts = [p['mpesa_receipt_number'] for p in response.json().get('results', response.json())]
        self.assertEqual(receipts, ['ABC123XYZ'])

    def test_payment_filter_by_method(self):
        Payment.objects.create(booking=self.booking, method=PaymentMethod.CASH, amount=Decimal('100'), status=PaymentStatus.SUCCESSFUL)
        Payment.objects.create(booking=self.other_booking, method=PaymentMethod.MPESA, amount=Decimal('100'), status=PaymentStatus.SUCCESSFUL)
        response = self.client.get('/api/payments/', {'method': PaymentMethod.CASH})
        methods = {p['method'] for p in response.json().get('results', response.json())}
        self.assertEqual(methods, {PaymentMethod.CASH})


class ParseAmountTests(TestCase):
    """Used at every offline-payment entry point instead of float(raw), which risks carrying
    binary floating-point imprecision into a value that flows straight into Decimal arithmetic
    and a DecimalField."""

    def test_parses_a_plain_string(self):
        self.assertEqual(parse_amount('2333.10'), Decimal('2333.10'))

    def test_parses_an_int_or_float_from_a_json_body(self):
        self.assertEqual(parse_amount(500), Decimal('500.00'))
        self.assertEqual(parse_amount(500.5), Decimal('500.50'))

    def test_quantizes_to_two_decimal_places(self):
        self.assertEqual(parse_amount('500'), Decimal('500.00'))

    def test_none_or_blank_raises_value_error(self):
        for bad in (None, ''):
            with self.assertRaises(ValueError):
                parse_amount(bad)

    def test_non_numeric_raises_value_error(self):
        for bad in ('abc', 'KES 500', [1, 2], True):
            with self.assertRaises(ValueError):
                parse_amount(bad)

    def test_zero_and_negative_parse_fine(self):
        # parse_amount only handles parsing - rejecting a non-positive amount is each caller's
        # own business-rule check, not this function's job.
        self.assertEqual(parse_amount('0'), Decimal('0.00'))
        self.assertEqual(parse_amount('-500'), Decimal('-500.00'))


class SitemapTests(APITestCase):
    def test_sitemap_is_valid_xml_with_static_pages(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        content = response.content.decode()
        self.assertIn('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', content)
        self.assertIn('<loc>http://localhost:5173/</loc>', content)
        self.assertIn('<loc>http://localhost:5173/fleet</loc>', content)

    def test_includes_a_visible_vehicle(self):
        vehicle = make_vehicle()
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(f'<loc>http://localhost:5173/fleet/{vehicle.id}</loc>', content)

    def test_excludes_a_vehicle_with_lapsed_insurance(self):
        vehicle = make_vehicle(insurance_expiry_date=timezone.now().date() - timedelta(days=1))
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn(f'<loc>http://localhost:5173/fleet/{vehicle.id}</loc>', content)

    def test_excludes_an_unavailable_vehicle(self):
        vehicle = make_vehicle(is_available=False)
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn(f'<loc>http://localhost:5173/fleet/{vehicle.id}</loc>', content)

    def test_includes_a_published_blog_post_and_excludes_a_draft(self):
        from blog.models import BlogPost

        published = BlogPost.objects.create(title='Published Post', excerpt='x', body='<p>x</p>', is_published=True)
        draft = BlogPost.objects.create(title='Draft Post', excerpt='x', body='<p>x</p>', is_published=False)
        content = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(f'<loc>http://localhost:5173/blog/{published.slug}</loc>', content)
        self.assertNotIn(f'<loc>http://localhost:5173/blog/{draft.slug}</loc>', content)


class ImpersonationTests(APITestCase):
    def setUp(self):
        self.platform_super = User.objects.create_superuser(username='platform-super@example.com', password='pass12345!')
        self.support_staff = User.objects.create_user(
            username='support@example.com', password='pass12345!', is_staff=True,
        )
        org = FleetPartner.objects.create(name='Org A', platform_fee_percent=Decimal('10'))
        self.org_admin = User.objects.create_user(
            username='org-admin@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=self.org_admin, organization=org)

        self.customer = User.objects.create_user(
            username='customer@example.com', email='customer@example.com',
            first_name='Jane', password='pass12345!',
        )
        self.driver_user = User.objects.create_user(username='driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Driver Sam', user=self.driver_user, is_active=True)

    def test_platform_superadmin_can_impersonate_a_customer(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/users/{self.customer.id}/impersonate/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)
        self.assertEqual(data['user']['email'], 'customer@example.com')
        self.assertEqual(data['user']['first_name'], 'Jane')

    def test_platform_superadmin_can_impersonate_a_driver_with_a_portal_account(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/users/{self.driver_user.id}/impersonate/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['user']['is_driver'])

    def test_impersonating_a_driver_yields_a_read_only_session(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/users/{self.driver_user.id}/impersonate/')
        access = response.json()['access']

        # Real Authorization header (not force_authenticate, which bypasses JWTAuthentication
        # entirely and would leave request.auth empty) - IsDriverUser reads the read_only claim
        # off request.auth, so this has to go through the real token parsing to prove anything.
        # force_authenticate(None) first: it otherwise silently overrides credentials() on the
        # same client instance, since it doesn't get cleared just by setting a header.
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        me_response = self.client.get('/api/auth/me/')
        self.assertTrue(me_response.json()['is_read_only_session'])

        read_response = self.client.get('/api/driver/bookings/mine/')
        self.assertEqual(read_response.status_code, 200)

        booking = make_booking(self.customer, make_vehicle(price_per_day=Decimal('1000')), driver=self.driver, status=BookingStatus.CONFIRMED)
        write_response = self.client.post(f'/api/driver/bookings/{booking.id}/acknowledge/')
        self.assertEqual(write_response.status_code, 403)
        booking.refresh_from_db()
        self.assertIsNone(booking.driver_acknowledged_at)

    def test_impersonating_a_customer_still_gets_full_read_write_access(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/users/{self.customer.id}/impersonate/')
        access = response.json()['access']

        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        me_response = self.client.get('/api/auth/me/')
        self.assertFalse(me_response.json()['is_read_only_session'])

    def test_cannot_impersonate_a_staff_account(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/users/{self.support_staff.id}/impersonate/')
        self.assertEqual(response.status_code, 400)

    def test_cannot_impersonate_another_superadmin(self):
        other_super = User.objects.create_superuser(username='other-super@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/users/{other_super.id}/impersonate/')
        self.assertEqual(response.status_code, 400)

    def test_org_admin_cannot_impersonate_anyone(self):
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post(f'/api/admin/users/{self.customer.id}/impersonate/')
        self.assertEqual(response.status_code, 403)

    def test_support_staff_cannot_impersonate_anyone(self):
        self.client.force_authenticate(user=self.support_staff)
        response = self.client.post(f'/api/admin/users/{self.customer.id}/impersonate/')
        self.assertEqual(response.status_code, 403)

    def test_impersonation_is_audit_logged(self):
        self.client.force_authenticate(user=self.platform_super)
        self.client.post(f'/api/admin/users/{self.customer.id}/impersonate/')
        entry = AuditLog.objects.filter(action='user.impersonate').first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.platform_super)

    def test_impersonation_refresh_token_expires_much_sooner_than_a_normal_login(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post(f'/api/admin/users/{self.customer.id}/impersonate/')
        refresh = RefreshToken(response.json()['refresh'])
        lifetime = refresh['exp'] - refresh['iat']
        self.assertLessEqual(lifetime, timedelta(hours=2).total_seconds())


class AdminHealthTests(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='health-staff@example.com', password='x', is_staff=True)
        self.customer = User.objects.create_user(username='health-customer@example.com', password='x')

    def test_support_staff_can_view_health(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/health/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for key in ('database', 'email', 'mpesa', 'storage', 'scheduler', 'error_tracking', 'debug_mode'):
            self.assertIn(key, data)
            self.assertIn('ok', data[key])

    def test_a_plain_customer_cannot_view_health(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/admin/health/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_view_health(self):
        response = self.client.get('/api/admin/health/')
        self.assertEqual(response.status_code, 401)

    def test_database_check_reports_ok(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/health/')
        self.assertTrue(response.json()['database']['ok'])


class AdminReferralSettingsTests(APITestCase):
    """Platform-superadmin-only, same tier as AdminFleetPartnerViewSet - a FleetPartner's own
    org-admin has no business changing a platform-wide referral credit amount."""

    def setUp(self):
        self.platform_super = User.objects.create_superuser(username='referral-settings-super@example.com', password='x')
        self.support_staff = User.objects.create_user(username='referral-settings-staff@example.com', password='x', is_staff=True)
        org = FleetPartner.objects.create(name='Referral Org', platform_fee_percent=Decimal('10'))
        self.org_admin = User.objects.create_user(
            username='referral-settings-org-admin@example.com', password='x', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=self.org_admin, organization=org)
        self.customer = User.objects.create_user(username='referral-settings-customer@example.com', password='x')

    def test_platform_superadmin_can_view_and_update_the_amount(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.get('/api/admin/referral-settings/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(str(response.data['credit_amount'])), Decimal('500'))

        response = self.client.patch('/api/admin/referral-settings/', {'credit_amount': '750'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(str(response.data['credit_amount'])), Decimal('750'))

        from accounts.models import ReferralSettings
        self.assertEqual(ReferralSettings.get_amount(), Decimal('750'))

    def test_updating_rejects_a_non_positive_amount(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.patch('/api/admin/referral-settings/', {'credit_amount': '0'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_response_includes_award_and_redemption_stats(self):
        from accounts.models import ReferralCredit

        other_user = User.objects.create_user(username='referral-settings-other@example.com', password='x')
        ReferralCredit.objects.create(user=self.customer, amount=Decimal('500'))
        booking = make_booking(other_user, make_vehicle())
        ReferralCredit.objects.create(user=self.customer, amount=Decimal('500'), redeemed_booking=booking)

        self.client.force_authenticate(user=self.platform_super)
        response = self.client.get('/api/admin/referral-settings/')
        self.assertEqual(response.data['credits_awarded_count'], 2)
        self.assertEqual(Decimal(str(response.data['credits_awarded_total'])), Decimal('1000'))
        self.assertEqual(response.data['credits_redeemed_count'], 1)
        self.assertEqual(Decimal(str(response.data['credits_redeemed_total'])), Decimal('500'))
        self.assertEqual(Decimal(str(response.data['credits_outstanding_total'])), Decimal('500'))

    def test_org_admin_cannot_view_or_update(self):
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.get('/api/admin/referral-settings/')
        self.assertEqual(response.status_code, 403)

        response = self.client.patch('/api/admin/referral-settings/', {'credit_amount': '999'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_support_staff_cannot_view_or_update(self):
        self.client.force_authenticate(user=self.support_staff)
        response = self.client.get('/api/admin/referral-settings/')
        self.assertEqual(response.status_code, 403)

    def test_plain_customer_cannot_view_or_update(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/admin/referral-settings/')
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_view(self):
        response = self.client.get('/api/admin/referral-settings/')
        self.assertEqual(response.status_code, 401)


class AdminLoyaltyTierTests(APITestCase):
    """Platform-superadmin-only, same tier as AdminReferralSettingsView - a FleetPartner's own
    org-admin has no business configuring a platform-wide rewards program."""

    def setUp(self):
        from accounts.models import LoyaltyTier

        self.platform_super = User.objects.create_superuser(username='loyalty-super@example.com', password='x')
        self.support_staff = User.objects.create_user(username='loyalty-staff@example.com', password='x', is_staff=True)
        org = FleetPartner.objects.create(name='Loyalty Org', platform_fee_percent=Decimal('10'))
        self.org_admin = User.objects.create_user(
            username='loyalty-org-admin@example.com', password='x', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=self.org_admin, organization=org)
        LoyaltyTier.objects.all().delete()

    def test_platform_superadmin_can_create_a_tier(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post('/api/admin/loyalty-tiers/', {
            'name': 'Silver', 'min_completed_trips': 3, 'discount_percent': '5',
        })
        self.assertEqual(response.status_code, 201)

        from accounts.models import LoyaltyTier
        self.assertTrue(LoyaltyTier.objects.filter(name='Silver').exists())

    def test_platform_superadmin_can_list_and_update_and_delete(self):
        from accounts.models import LoyaltyTier

        tier = LoyaltyTier.objects.create(name='Bronze', min_completed_trips=0, discount_percent=Decimal('0'))
        self.client.force_authenticate(user=self.platform_super)

        response = self.client.get('/api/admin/loyalty-tiers/')
        self.assertEqual(response.status_code, 200)

        response = self.client.patch(f'/api/admin/loyalty-tiers/{tier.id}/', {'discount_percent': '2'}, format='json')
        self.assertEqual(response.status_code, 200)
        tier.refresh_from_db()
        self.assertEqual(tier.discount_percent, Decimal('2.00'))

        response = self.client.delete(f'/api/admin/loyalty-tiers/{tier.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(LoyaltyTier.objects.filter(pk=tier.id).exists())

    def test_discount_percent_must_be_between_0_and_100(self):
        self.client.force_authenticate(user=self.platform_super)
        response = self.client.post('/api/admin/loyalty-tiers/', {
            'name': 'Overboard', 'min_completed_trips': 1, 'discount_percent': '150',
        })
        self.assertEqual(response.status_code, 400)

    def test_org_admin_cannot_manage_tiers(self):
        self.client.force_authenticate(user=self.org_admin)
        response = self.client.post('/api/admin/loyalty-tiers/', {
            'name': 'Silver', 'min_completed_trips': 3, 'discount_percent': '5',
        })
        self.assertEqual(response.status_code, 403)

    def test_support_staff_cannot_manage_tiers(self):
        self.client.force_authenticate(user=self.support_staff)
        response = self.client.post('/api/admin/loyalty-tiers/', {
            'name': 'Silver', 'min_completed_trips': 3, 'discount_percent': '5',
        })
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_view(self):
        response = self.client.get('/api/admin/loyalty-tiers/')
        self.assertEqual(response.status_code, 401)


def _make_test_image(size, mode='RGB', fmt='JPEG'):
    """A genuinely valid, decodable image (unlike the placeholder-bytes fixtures used
    elsewhere in this file, which only need to satisfy "a file was uploaded", not
    "Pillow can actually open this") - needed to exercise optimize_image()'s real resize path."""
    buffer = BytesIO()
    img = PILImage.new(mode, size, color=(200, 50, 50) if mode == 'RGB' else (200, 50, 50, 128))
    img.save(buffer, format=fmt)
    buffer.seek(0)
    ext = 'jpg' if fmt == 'JPEG' else fmt.lower()
    return SimpleUploadedFile(f'test.{ext}', buffer.read(), content_type=f'image/{fmt.lower()}')


class OptimizeImageTests(TestCase):
    def test_resizes_an_oversized_image_down(self):
        vehicle = make_vehicle(image=_make_test_image((3000, 2000)))
        with PILImage.open(vehicle.image) as saved:
            self.assertLessEqual(max(saved.size), 1600)
            # Aspect ratio preserved (3000x2000 = 3:2)
            self.assertAlmostEqual(saved.width / saved.height, 3000 / 2000, places=1)

    def test_does_not_upscale_a_small_image(self):
        vehicle = make_vehicle(image=_make_test_image((400, 300)))
        with PILImage.open(vehicle.image) as saved:
            self.assertEqual(saved.size, (400, 300))

    def test_converts_opaque_image_to_jpeg(self):
        vehicle = make_vehicle(image=_make_test_image((400, 300)))
        self.assertTrue(vehicle.image.name.endswith('.jpg'))

    def test_keeps_a_transparent_image_as_png(self):
        vehicle = make_vehicle(image=_make_test_image((400, 300), mode='RGBA', fmt='PNG'))
        self.assertTrue(vehicle.image.name.endswith('.png'))

    def test_strips_exif_data(self):
        buffer = BytesIO()
        img = PILImage.new('RGB', (400, 300), color=(10, 20, 30))
        exif = img.getexif()
        exif[0x0110] = 'Test Camera Model'  # Model tag - a stand-in for real GPS/camera EXIF
        img.save(buffer, format='JPEG', exif=exif)
        buffer.seek(0)
        upload = SimpleUploadedFile('withexif.jpg', buffer.read(), content_type='image/jpeg')

        vehicle = make_vehicle(image=upload)
        with PILImage.open(vehicle.image) as saved:
            self.assertFalse(saved.getexif())

    def test_a_file_pillow_cannot_parse_is_saved_unmodified_rather_than_crashing(self):
        # Same shape as the placeholder-bytes fixtures used elsewhere in this test suite -
        # confirms the app-wide contract (an upload never 500s just because optimization failed)
        # rather than re-testing every individual call site.
        bogus = SimpleUploadedFile('bogus.jpg', b'not a real image', content_type='image/jpeg')
        vehicle = make_vehicle(image=bogus)
        self.assertEqual(vehicle.image.read(), b'not a real image')


class AdminBookingExportTests(APITestCase):
    """CSV download of the booking list for accounting/tax/reconciliation work outside the app -
    reuses AdminBookingViewSet.get_queryset(), so it inherits the same org-scoping and search/
    status/service_type filters the list view already has."""

    def setUp(self):
        import csv
        self.csv = csv

        self.staff = User.objects.create_user(username='bexport-staff@example.com', password='pass12345!', is_staff=True)
        self.customer = User.objects.create_user(username='bexport-customer@example.com', password='pass12345!', email='bexport-customer@example.com')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.booking = make_booking(self.customer, self.vehicle, status=BookingStatus.PENDING)

    def _rows(self, response):
        return list(self.csv.reader(response.content.decode('utf-8').splitlines()))

    def test_support_staff_can_export_bookings_as_csv(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/bookings/export/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        rows = self._rows(response)
        self.assertEqual(rows[0][0], 'ID')
        self.assertEqual(len(rows), 2)  # header + one booking
        self.assertIn('Jane Doe', rows[1])

    def test_plain_customer_cannot_export_bookings(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/admin/bookings/export/')
        self.assertEqual(response.status_code, 403)

    def test_status_filter_narrows_the_export(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/bookings/export/?status=cancelled')
        rows = self._rows(response)
        self.assertEqual(len(rows), 1)  # header only - this booking is pending, not cancelled

    def test_malformed_date_is_rejected(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/bookings/export/?start_date=bogus')
        self.assertEqual(response.status_code, 400)

    def test_org_admin_only_exports_their_own_organizations_bookings(self):
        org = FleetPartner.objects.create(name='Bexport Org', platform_fee_percent=Decimal('10'))
        org_admin = User.objects.create_user(
            username='bexport-org-admin@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=org_admin, organization=org)
        self.client.force_authenticate(user=org_admin)
        response = self.client.get('/api/admin/bookings/export/')
        rows = self._rows(response)
        self.assertEqual(len(rows), 1)  # header only - this booking belongs to a different org


class AdminPayoutExportTests(APITestCase):
    """CSV download of the driver payout ledger - reuses AdminDriverPayoutViewSet.get_queryset(),
    so it's already org-scoped the same way the list view is."""

    def setUp(self):
        import csv
        self.csv = csv

        self.staff = User.objects.create_user(username='pexport-staff@example.com', password='pass12345!', is_staff=True)
        self.customer = User.objects.create_user(username='pexport-customer@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Export Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )
        self.booking.confirm_if_deposit_met()
        self.payout = DriverPayout.objects.get(booking=self.booking)

    def _rows(self, response):
        return list(self.csv.reader(response.content.decode('utf-8').splitlines()))

    def test_support_staff_can_export_payouts_as_csv(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.get('/api/admin/payouts/export/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        rows = self._rows(response)
        self.assertEqual(rows[0][0], 'ID')
        self.assertEqual(len(rows), 2)  # header + one payout
        self.assertIn('Export Driver', rows[1])

    def test_plain_customer_cannot_export_payouts(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get('/api/admin/payouts/export/')
        self.assertEqual(response.status_code, 403)

    def test_recipient_filter_isolates_fleet_partner_payouts(self):
        org = FleetPartner.objects.create(name='Filter Org', platform_fee_percent=Decimal('10'))
        org_vehicle = make_vehicle(name='Filter Org Car', owner=org, is_company_owned=False, price_per_day=Decimal('1000'))
        org_customer = User.objects.create_user(username='pexport-org-customer@example.com', password='pass12345!')
        org_booking = make_booking(org_customer, org_vehicle, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=org_booking, method=PaymentMethod.MPESA, amount=org_booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        org_booking.confirm_if_deposit_met()

        self.client.force_authenticate(user=self.staff)

        fleet_rows = self._rows(self.client.get('/api/admin/payouts/export/?recipient=fleet'))
        self.assertEqual(len(fleet_rows), 2)  # header + the org payout only
        self.assertIn('Filter Org', fleet_rows[1])

        driver_rows = self._rows(self.client.get('/api/admin/payouts/export/?recipient=driver'))
        self.assertEqual(len(driver_rows), 2)  # header + the driver payout only
        self.assertIn('Export Driver', driver_rows[1])

    def test_org_admin_only_exports_their_own_organizations_payouts(self):
        org = FleetPartner.objects.create(name='Pexport Org', platform_fee_percent=Decimal('10'))
        org_admin = User.objects.create_user(
            username='pexport-org-admin@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=org_admin, organization=org)
        self.client.force_authenticate(user=org_admin)
        response = self.client.get('/api/admin/payouts/export/')
        rows = self._rows(response)
        self.assertEqual(len(rows), 1)  # header only - this payout belongs to a different org


class AdminPhoneNumberValidationTests(APITestCase):
    """Every admin-facing entry point that accepts a phone number enforces the same Kenyan
    mobile format (254 + 7 or 1 + 8 digits) as customer-facing registration - see
    core.validators.validate_kenyan_phone_number."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='phone-super@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.superadmin)

    def test_admin_creating_a_driver_rejects_a_malformed_phone_number(self):
        response = self.client.post('/api/admin/drivers/', {
            'full_name': 'New Driver', 'phone_number': '0712345678',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone_number', response.json())

    def test_admin_creating_a_driver_accepts_a_valid_phone_number(self):
        response = self.client.post('/api/admin/drivers/', {
            'full_name': 'New Driver', 'phone_number': '254712345678',
        }, format='json')
        self.assertEqual(response.status_code, 201)

    def test_admin_creating_a_driver_with_no_phone_number_still_works(self):
        # Driver.phone_number stays optional at the model level - only its format is enforced.
        response = self.client.post('/api/admin/drivers/', {'full_name': 'New Driver'}, format='json')
        self.assertEqual(response.status_code, 201)

    def test_admin_editing_a_customers_phone_number_rejects_a_malformed_value(self):
        customer = User.objects.create_user(username='phone-customer@example.com', password='pass12345!')
        CustomerProfile.objects.create(user=customer, phone_number='254700000000')
        response = self.client.patch(f'/api/admin/users/{customer.id}/', {'phone_number': '999'}, format='json')
        self.assertEqual(response.status_code, 400)
        customer.customer_profile.refresh_from_db()
        self.assertEqual(customer.customer_profile.phone_number, '254700000000')  # unchanged

    def test_admin_creating_a_customer_account_rejects_a_malformed_phone_number(self):
        response = self.client.post('/api/admin/users/', {
            'full_name': 'New Customer', 'email': 'new-customer@example.com',
            'phone_number': '0712345678', 'password': 'pass12345!',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone_number', response.json())

    def test_admin_creating_a_fleet_partner_rejects_a_malformed_contact_phone(self):
        response = self.client.post('/api/admin/fleet-partners/', {
            'name': 'New Partner', 'contact_phone': '12345', 'platform_fee_percent': '10',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('contact_phone', response.json())

    def test_admin_creating_a_fleet_partner_rejects_a_malformed_payout_phone_number(self):
        response = self.client.post('/api/admin/fleet-partners/', {
            'name': 'New Partner', 'payout_phone_number': '254999999999', 'platform_fee_percent': '10',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('payout_phone_number', response.json())


class ReportClientErrorTests(APITestCase):
    """core.views.ReportClientErrorView - the no-Sentry-required side of frontend error
    visibility (see frontend/src/utils/clientErrorReporting.js)."""

    def test_anonymous_visitor_can_report_an_error(self):
        response = self.client.post('/api/report-client-error/', {
            'message': 'TypeError: cannot read property of undefined',
            'stack': 'at BookingView.vue:42',
            'url': 'https://silverlakecarentals.com/book/5',
        }, format='json')
        self.assertEqual(response.status_code, 204)

    def test_missing_fields_do_not_crash(self):
        response = self.client.post('/api/report-client-error/', {}, format='json')
        self.assertEqual(response.status_code, 204)

    @override_settings(ADMINS=[('Test Admin', 'admin-alerts@example.com')])
    def test_emails_admins_when_admin_error_email_is_configured(self):
        mail.outbox = []
        self.client.post('/api/report-client-error/', {
            'message': 'ReferenceError: x is not defined', 'stack': 'at HomeView.vue:10',
            'url': 'https://silverlakecarentals.com/',
        }, format='json')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('admin-alerts@example.com', mail.outbox[0].to)
        self.assertIn('ReferenceError', mail.outbox[0].subject)

    def test_does_not_email_when_no_admins_configured(self):
        # settings.ADMINS defaults to [] when ADMIN_ERROR_EMAIL is unset - confirms this view
        # doesn't blow up or misbehave in that (default) state.
        mail.outbox = []
        self.client.post('/api/report-client-error/', {'message': 'x', 'stack': 'y'}, format='json')
        self.assertEqual(len(mail.outbox), 0)

    def test_repeated_requests_are_throttled(self):
        cache.clear()
        original = ScopedRateThrottle.THROTTLE_RATES.get('client-error-report')
        ScopedRateThrottle.THROTTLE_RATES['client-error-report'] = '2/min'
        try:
            for _ in range(2):
                self.client.post('/api/report-client-error/', {'message': 'x'}, format='json')
            response = self.client.post('/api/report-client-error/', {'message': 'x'}, format='json')
        finally:
            ScopedRateThrottle.THROTTLE_RATES['client-error-report'] = original
        self.assertEqual(response.status_code, 429)

    def test_report_is_persisted_for_an_anonymous_visitor(self):
        self.client.post('/api/report-client-error/', {
            'message': 'TypeError: cannot read property of undefined',
            'stack': 'at RegisterView.vue:88',
            'url': 'https://silverlakecarentals.com/register',
        }, format='json')

        report = ClientErrorReport.objects.get(message='TypeError: cannot read property of undefined')
        self.assertIsNone(report.user)
        self.assertEqual(report.stack, 'at RegisterView.vue:88')
        self.assertEqual(report.url, 'https://silverlakecarentals.com/register')

    def test_report_is_tied_to_the_authenticated_user(self):
        customer = User.objects.create_user(username='client-err@example.com', password='pass12345!')
        self.client.force_authenticate(user=customer)
        self.client.post('/api/report-client-error/', {'message': 'Signup failed unexpectedly'}, format='json')

        report = ClientErrorReport.objects.get(message='Signup failed unexpectedly')
        self.assertEqual(report.user, customer)

    def test_missing_fields_still_persist_a_report(self):
        self.client.post('/api/report-client-error/', {}, format='json')
        self.assertTrue(ClientErrorReport.objects.filter(message='(no message)').exists())


class AdminClientErrorReportViewSetTests(APITestCase):
    """The System Health page's "Recent Client Errors" table - lets staff see a specific
    visitor's exact error (including during signup) instead of grepping server logs."""

    def setUp(self):
        self.platform_staff = User.objects.create_user(
            username='platform-staff-err@example.com', password='pass12345!', is_staff=True,
        )
        self.report = ClientErrorReport.objects.create(
            message='Network Error', stack='at apiClient', url='https://silverlakecarentals.com/register',
        )

    def test_platform_staff_can_list_reports(self):
        self.client.force_authenticate(user=self.platform_staff)
        response = self.client.get('/api/admin/client-errors/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['message'], 'Network Error')

    def test_org_admin_cannot_view_client_error_reports(self):
        org = FleetPartner.objects.create(name='Client Error Org', platform_fee_percent=Decimal('10'))
        org_admin = User.objects.create_user(
            username='org-admin-err@example.com', password='pass12345!', is_staff=True, is_superuser=True,
        )
        StaffOrganization.objects.create(user=org_admin, organization=org)

        self.client.force_authenticate(user=org_admin)
        response = self.client.get('/api/admin/client-errors/')
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_cannot_view_client_error_reports(self):
        response = self.client.get('/api/admin/client-errors/')
        self.assertEqual(response.status_code, 401)

    def test_report_shows_the_reporting_users_email(self):
        customer = User.objects.create_user(
            username='reporter@example.com', email='reporter@example.com', password='pass12345!',
        )
        ClientErrorReport.objects.create(user=customer, message='Booking crash')

        self.client.force_authenticate(user=self.platform_staff)
        response = self.client.get('/api/admin/client-errors/')
        entry = next(r for r in response.data['results'] if r['message'] == 'Booking crash')
        self.assertEqual(entry['user_email'], 'reporter@example.com')
