from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from bookings.models import BookingStatus
from bookings.tests import make_booking, make_vehicle
from drivers.models import Driver
from payments.models import DriverPayout, Payment, PaymentMethod, PaymentStatus

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

        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )
        self.booking.confirm_if_deposit_met()
        self.payout = DriverPayout.objects.get(booking=self.booking)
        assert self.payout.needs_verification and not self.payout.is_verified

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
        self.client.force_authenticate(user=self.superadmin)

        verify_response = self.client.post(f'/api/admin/payouts/{self.payout.id}/verify/')
        self.assertEqual(verify_response.status_code, 200)
        self.payout.refresh_from_db()
        self.assertTrue(self.payout.is_verified)
        self.assertIsNotNone(self.payout.verified_at)

        pay_response = self.client.post(
            f'/api/admin/payouts/{self.payout.id}/mark-paid/', {'payout_reference': 'MPESA123'},
        )
        self.assertEqual(pay_response.status_code, 200)
        self.payout.refresh_from_db()
        self.assertTrue(self.payout.is_paid)

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
