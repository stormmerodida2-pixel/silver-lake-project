from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import BookingStatus
from bookings.tests import make_booking, make_vehicle
from drivers.models import Driver, DriverApplication
from fleet.models import FleetPartner, Vehicle, VehicleCategory, VehicleImage, VehicleServiceRecord, VehicleSubmission
from payments.models import DriverPayout, Payment, PaymentMethod, PaymentStatus, Refund

from .models import AuditLog, StaffOrganization
from .utils import parse_amount

User = get_user_model()


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
