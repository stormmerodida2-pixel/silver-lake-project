import threading
import time
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import ScopedRateThrottle

from drivers.models import Driver
from fleet.models import FleetPartner, Vehicle, VehicleCategory
from payments.models import DriverPayout, Payment, PaymentMethod, PaymentStatus, Refund
from reviews.models import Review

from .models import Booking, BookingSource, BookingStatus, ServiceType, VehicleConditionReport

User = get_user_model()

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)
NEXT_WEEK = TODAY + timedelta(days=7)


def make_vehicle(**kwargs):
    if 'category' not in kwargs:
        kwargs['category'], _ = VehicleCategory.objects.get_or_create(
            slug='compact_sedan', defaults={'name': 'Compact Sedan'},
        )
    defaults = dict(
        name='Test Car', passenger_capacity=4,
        price_per_day=Decimal('1000'), is_available=True,
    )
    # A vehicle created with a driver is assumed to be that driver's own car (matching the
    # driver-onboarding flow, where is_company_owned=False), unless a test says otherwise -
    # most existing tests rely on this to exercise the driver-payout path.
    if kwargs.get('driver') is not None and 'is_company_owned' not in kwargs:
        defaults['is_company_owned'] = False
    defaults.update(kwargs)
    return Vehicle.objects.create(**defaults)


def make_booking(user, vehicle, driver=None, **kwargs):
    defaults = dict(
        user=user, vehicle=vehicle, driver=driver, service_type=ServiceType.WITH_DRIVER,
        customer_name='Jane Doe', customer_phone='254700000000',
        pickup_location='Kisumu', start_date=TOMORROW, end_date=NEXT_WEEK,
    )
    defaults.update(kwargs)
    booking = Booking(**defaults)
    booking.save()
    return booking


class BookingValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='jane@example.com', password='pass12345!')
        self.vehicle = make_vehicle()

    def test_end_date_before_start_date_is_rejected(self):
        booking = Booking(
            user=self.user, vehicle=self.vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=NEXT_WEEK, end_date=TOMORROW,
        )
        with self.assertRaises(ValidationError):
            booking.clean()

    def test_a_new_booking_cannot_start_in_the_past(self):
        booking = Booking(
            user=self.user, vehicle=self.vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=TODAY - timedelta(days=1), end_date=NEXT_WEEK,
        )
        with self.assertRaises(ValidationError):
            booking.clean()

    def test_an_existing_bookings_start_date_is_not_revalidated_on_later_edits(self):
        booking = make_booking(self.user, self.vehicle, start_date=TOMORROW, end_date=NEXT_WEEK)
        booking.start_date = TODAY - timedelta(days=1)  # simulate time having passed
        booking.notes = 'Updated note'
        booking.clean()  # should not raise - only new bookings are checked

    def test_self_drive_requires_license_and_id_documents(self):
        booking = Booking(
            user=self.user, vehicle=self.vehicle, service_type=ServiceType.SELF_DRIVE,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=TOMORROW, end_date=NEXT_WEEK, customer_license_number='DL123',
        )
        with self.assertRaises(ValidationError):
            booking.clean()

        booking.customer_license_document = SimpleUploadedFile('license.pdf', b'x', content_type='application/pdf')
        booking.customer_id_document = SimpleUploadedFile('id.pdf', b'x', content_type='application/pdf')
        booking.clean()  # should not raise now

    def test_overlapping_dates_on_same_vehicle_are_rejected(self):
        make_booking(self.user, self.vehicle, status=BookingStatus.CONFIRMED)
        conflicting = Booking(
            user=self.user, vehicle=self.vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=TOMORROW, end_date=NEXT_WEEK,
        )
        with self.assertRaises(ValidationError):
            conflicting.clean()

    def test_cancelled_bookings_dont_block_the_same_dates(self):
        make_booking(self.user, self.vehicle, status=BookingStatus.CANCELLED)
        non_conflicting = Booking(
            user=self.user, vehicle=self.vehicle, service_type=ServiceType.WITH_DRIVER,
            customer_name='Jane', customer_phone='254700000000', pickup_location='Kisumu',
            start_date=TOMORROW, end_date=NEXT_WEEK,
        )
        non_conflicting.clean()  # should not raise


class BookingMoneyMathTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='jane@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Driver One', is_active=True)
        # Driver-owned (is_company_owned=False via make_vehicle's driver-kwarg default) - this
        # class is testing payout math itself, which only applies when the driver owns the
        # vehicle; see PlatformFeeOwnershipTests for the company-owned/FleetPartner-owned cases.
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'), driver=self.driver)

    def test_deposit_is_30_percent_of_total(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver)
        # 7 nights inclusive -> rental_days = 7
        self.assertEqual(booking.rental_days, 7)
        self.assertEqual(booking.total_amount, Decimal('7000'))
        self.assertEqual(booking.deposit_amount, Decimal('2100.00'))

    def test_platform_fee_only_applies_to_with_driver_bookings(self):
        with_driver = make_booking(self.user, self.vehicle, driver=self.driver, service_type=ServiceType.WITH_DRIVER)
        self.assertGreater(with_driver.platform_fee_amount, 0)
        self.assertEqual(with_driver.driver_payout_amount, with_driver.total_amount - with_driver.platform_fee_amount)

        self_drive = make_booking(
            self.user, self.vehicle, driver=None, service_type=ServiceType.SELF_DRIVE,
            customer_license_document=SimpleUploadedFile('l.pdf', b'x'),
            customer_id_document=SimpleUploadedFile('i.pdf', b'x'),
            start_date=TOMORROW + timedelta(days=30), end_date=NEXT_WEEK + timedelta(days=30),
        )
        self.assertEqual(self_drive.platform_fee_amount, 0)
        self.assertEqual(self_drive.driver_payout_amount, 0)

    def test_is_deposit_paid_reflects_successful_payments_only(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver)
        self.assertFalse(booking.is_deposit_paid)

        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.PENDING)
        self.assertFalse(booking.is_deposit_paid)

        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)
        self.assertTrue(booking.is_deposit_paid)
        self.assertEqual(booking.balance_due, booking.total_amount - booking.deposit_amount)

    def test_confirm_if_deposit_met_only_confirms_once(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver)
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)

        booking.confirm_if_deposit_met()
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)

        # Calling again should be a no-op, not raise or re-send the confirmation email.
        booking.confirm_if_deposit_met()
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)

    def test_confirming_notifies_the_client_in_app_exactly_once(self):
        from notifications.models import Notification, NotificationEvent

        booking = make_booking(self.user, self.vehicle, driver=self.driver)
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)

        booking.confirm_if_deposit_met()
        booking.confirm_if_deposit_met()  # should not notify a second time

        notification = Notification.objects.get(event=NotificationEvent.BOOKING_CONFIRMED)
        self.assertEqual(notification.user_id, self.user.id)
        self.assertIn(str(booking.id), notification.message)

    def test_payout_is_not_created_until_the_booking_is_fully_paid(self):
        """The driver's payout is calculated on the whole trip value, so it shouldn't be queued
        while the business has only collected a fraction of that (e.g. just the deposit)."""
        booking = make_booking(self.user, self.vehicle, driver=self.driver)
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)

        booking.confirm_if_deposit_met()
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)  # deposit is enough to confirm...
        self.assertFalse(DriverPayout.objects.filter(booking=booking).exists())  # ...but not to pay out

        # Paying off the remaining balance later should create the payout, exactly once.
        Payment.objects.create(booking=booking, amount=booking.balance_due, status=PaymentStatus.SUCCESSFUL)
        booking.confirm_if_deposit_met()
        self.assertEqual(booking.driver_payout.amount, booking.driver_payout_amount)

        booking.confirm_if_deposit_met()  # calling again shouldn't duplicate it
        self.assertEqual(booking.driver.payouts.filter(booking=booking).count(), 1)


class ReferralCreditAwardTests(TestCase):
    """A referrer earns credit the moment their referred friend's *first* booking is confirmed
    (deposit paid) - not on registration, and not again on a later booking. See
    Booking._award_referral_credit_if_first_booking / accounts.services.award_referral_credit."""

    def setUp(self):
        from accounts.models import CustomerProfile

        self.referrer = User.objects.create_user(username='referrer@example.com', password='x')
        CustomerProfile.objects.create(user=self.referrer)
        self.referred_user = User.objects.create_user(username='referred@example.com', password='x', first_name='Alex')
        CustomerProfile.objects.create(user=self.referred_user, referred_by=self.referrer)
        self.vehicle = make_vehicle()

    def test_referrers_first_booking_confirmation_awards_credit(self):
        from accounts.models import ReferralCredit, ReferralSettings

        booking = make_booking(self.referred_user, self.vehicle)
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)

        booking.confirm_if_deposit_met()

        credit = ReferralCredit.objects.get(user=self.referrer)
        self.assertEqual(credit.amount, ReferralSettings.get_amount())
        self.assertEqual(credit.referred_user_id, self.referred_user.id)
        self.assertFalse(credit.is_redeemed)

    def test_a_second_booking_by_the_same_referred_user_does_not_award_again(self):
        from accounts.models import ReferralCredit

        first_booking = make_booking(self.referred_user, self.vehicle, start_date=TOMORROW, end_date=TOMORROW + timedelta(days=2))
        Payment.objects.create(booking=first_booking, amount=first_booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)
        first_booking.confirm_if_deposit_met()

        second_booking = make_booking(
            self.referred_user, self.vehicle,
            start_date=TOMORROW + timedelta(days=10), end_date=TOMORROW + timedelta(days=12),
        )
        Payment.objects.create(booking=second_booking, amount=second_booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)
        second_booking.confirm_if_deposit_met()

        self.assertEqual(ReferralCredit.objects.filter(user=self.referrer).count(), 1)

    def test_a_user_with_no_referrer_awards_nothing(self):
        from accounts.models import ReferralCredit

        unreferred_user = User.objects.create_user(username='unreferred@example.com', password='x')
        booking = make_booking(unreferred_user, self.vehicle)
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)

        booking.confirm_if_deposit_met()

        self.assertEqual(ReferralCredit.objects.count(), 0)

    def test_in_app_notification_sent_to_the_referrer(self):
        from notifications.models import Notification, NotificationEvent

        booking = make_booking(self.referred_user, self.vehicle)
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)
        booking.confirm_if_deposit_met()

        notification = Notification.objects.get(event=NotificationEvent.REFERRAL_CREDIT_EARNED)
        self.assertEqual(notification.user_id, self.referrer.id)


class PlatformFeeOwnershipTests(TestCase):
    """SilverLake owns most of its own fleet - a driver merely assigned to drive a
    company-owned vehicle is an employee/operator, not an owner, so there's no 85% payout to
    them; the full fare is SilverLake's. Only an individual driver-partner's own car (or,
    eventually, a FleetPartner-owned one) creates a payout at all."""

    def setUp(self):
        self.user = User.objects.create_user(username='ownership@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Ownership Driver', is_active=True)

    def _paid_booking(self, vehicle):
        booking = make_booking(self.user, vehicle, driver=self.driver, service_type=ServiceType.WITH_DRIVER)
        Payment.objects.create(booking=booking, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL)
        booking.confirm_if_deposit_met()
        return booking

    def test_company_owned_vehicle_creates_no_payout(self):
        vehicle = make_vehicle(name='Company Car', driver=self.driver, is_company_owned=True)
        booking = self._paid_booking(vehicle)
        self.assertEqual(booking.platform_fee_amount, 0)
        self.assertEqual(booking.driver_payout_amount, 0)
        self.assertFalse(DriverPayout.objects.filter(booking=booking).exists())

    def test_driver_owned_vehicle_still_creates_the_85_15_payout(self):
        vehicle = make_vehicle(name='Own Car', driver=self.driver, is_company_owned=False)
        booking = self._paid_booking(vehicle)
        self.assertGreater(booking.platform_fee_amount, 0)
        self.assertEqual(booking.driver_payout_amount, booking.total_amount - booking.platform_fee_amount)
        self.assertTrue(DriverPayout.objects.filter(booking=booking).exists())

    def test_fleet_partner_owned_vehicle_pays_out_to_the_organization_not_the_driver(self):
        # A driver merely operating a FleetPartner's vehicle never gets an individual cut - the
        # payout goes to the organization, at that partner's own negotiated rate, not the fixed
        # 15% individual driver-partner rate.
        partner = FleetPartner.objects.create(name='Some Fleet Co', platform_fee_percent=Decimal('10'))
        vehicle = make_vehicle(name='Partner Car', driver=self.driver, is_company_owned=False, owner=partner)
        booking = self._paid_booking(vehicle)
        self.assertEqual(booking.platform_fee_amount, booking.total_amount * Decimal('10') / Decimal('100'))
        self.assertEqual(booking.driver_payout_amount, booking.total_amount - booking.platform_fee_amount)

        payout = DriverPayout.objects.get(booking=booking)
        self.assertIsNone(payout.driver_id)
        self.assertEqual(payout.organization_id, partner.id)
        self.assertEqual(payout.amount, booking.driver_payout_amount)

    def test_self_drive_booking_never_creates_a_payout_regardless_of_ownership(self):
        vehicle = make_vehicle(name='Self Drive Car', driver=self.driver, is_company_owned=False)
        booking = make_booking(
            self.user, vehicle, driver=None, service_type=ServiceType.SELF_DRIVE,
            customer_license_document=SimpleUploadedFile('l.pdf', b'x'),
            customer_id_document=SimpleUploadedFile('i.pdf', b'x'),
        )
        self.assertEqual(booking.platform_fee_amount, 0)
        self.assertEqual(booking.driver_payout_amount, 0)

    def test_vehicles_created_via_driver_onboarding_are_not_company_owned(self):
        from drivers.models import ApplicationStatus, DriverApplication

        application = DriverApplication.objects.create(
            full_name='Onboard Driver', email='onboard@example.com', phone_number='254700000000',
            years_of_experience=3, vehicle_name='Onboard Car',
            vehicle_category=VehicleCategory.objects.create(name='Onboard Category'),
            passenger_capacity=4, price_per_day=Decimal('1000'),
            status=ApplicationStatus.PENDING,
        )
        application.approve()
        self.assertFalse(application.created_vehicle.is_company_owned)


class BookingCancelActionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='jane@example.com', password='pass12345!')
        self.vehicle = make_vehicle()
        self.client.force_authenticate(user=self.user)

    def test_customer_cannot_hard_delete_their_own_booking(self):
        # Deleting (vs. cancelling) would cascade-delete any Payment/DriverPayout/Refund tied
        # to it - "removing" a booking is always cancel(), never destroy().
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.delete(f'/api/bookings/{booking.id}/')
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Booking.objects.filter(id=booking.id).exists())

    def test_can_cancel_a_pending_booking(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.post(f'/api/bookings/{booking.id}/cancel/')
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)

    def test_cancelling_a_booking_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        self.client.post(f'/api/bookings/{booking.id}/cancel/')
        notification = Notification.objects.get(event=NotificationEvent.BOOKING_CANCELLED, user__isnull=True)
        self.assertIn(str(booking.id), notification.message)

    def test_cancelling_a_booking_notifies_the_client_in_app(self):
        from notifications.models import Notification, NotificationEvent

        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        self.client.post(f'/api/bookings/{booking.id}/cancel/')
        notification = Notification.objects.get(event=NotificationEvent.BOOKING_CANCELLED, user_id=self.user.id)
        self.assertIn(str(booking.id), notification.message)

    def test_cannot_cancel_a_completed_booking(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.COMPLETED)
        response = self.client.post(f'/api/bookings/{booking.id}/cancel/')
        self.assertEqual(response.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)

    def test_cannot_cancel_an_already_cancelled_booking(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.CANCELLED)
        response = self.client.post(f'/api/bookings/{booking.id}/cancel/')
        self.assertEqual(response.status_code, 400)

    def test_customer_cannot_cancel_someone_elses_booking(self):
        other_user = User.objects.create_user(username='other@example.com', password='pass12345!')
        booking = make_booking(other_user, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.post(f'/api/bookings/{booking.id}/cancel/')
        self.assertEqual(response.status_code, 404)  # not in this user's queryset

    def test_cancelling_an_unpaid_booking_creates_no_refund(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        self.client.post(f'/api/bookings/{booking.id}/cancel/')
        self.assertFalse(Refund.objects.filter(booking=booking).exists())

    def test_cancelling_a_paid_booking_creates_a_refund_record(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA,
            amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.client.post(f'/api/bookings/{booking.id}/cancel/')
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, booking.deposit_amount)
        self.assertEqual(refund.status, 'pending')

    def test_cancelling_a_fully_paid_booking_voids_its_unpaid_driver_payout(self):
        driver = Driver.objects.create(full_name='Cancel Driver', is_active=True)
        driver_owned_vehicle = make_vehicle(name='Cancel Driver Car', driver=driver)
        booking = make_booking(self.user, driver_owned_vehicle, driver=driver, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA,
            amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()
        payout = DriverPayout.objects.get(booking=booking)
        self.assertFalse(payout.is_voided)

        self.client.post(f'/api/bookings/{booking.id}/cancel/')
        payout.refresh_from_db()
        self.assertTrue(payout.is_voided)

    def test_a_payment_confirmed_after_cancellation_does_not_queue_a_payout(self):
        # Simulates an STK push that was already in flight before the customer cancelled -
        # Safaricom's callback can still confirm it successful after the fact.
        driver = Driver.objects.create(full_name='Late Payment Driver', is_active=True)
        booking = make_booking(self.user, self.vehicle, driver=driver, status=BookingStatus.PENDING)
        booking.mark_cancelled()

        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA,
            amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()

        self.assertFalse(DriverPayout.objects.filter(booking=booking).exists())

    def test_a_payment_confirmed_after_cancellation_updates_the_pending_refund(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA,
            amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.mark_cancelled()
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, booking.deposit_amount)

        # More money lands after cancellation (e.g. a second STK push that was already sent).
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA,
            amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()

        refund.refresh_from_db()
        self.assertEqual(refund.amount, booking.amount_paid)

    def test_an_already_issued_refund_is_not_changed_by_a_late_payment(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA,
            amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.mark_cancelled()
        refund = Refund.objects.get(booking=booking)
        refund.mark_issued(reference='REFUND123')
        original_amount = refund.amount

        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA,
            amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()

        refund.refresh_from_db()
        self.assertEqual(refund.amount, original_amount)

    def test_cancelling_a_booking_emails_the_customer(self):
        booking = make_booking(
            self.user, self.vehicle, status=BookingStatus.PENDING, customer_email='jane@example.com',
        )
        mail.outbox = []
        self.client.post(f'/api/bookings/{booking.id}/cancel/')
        cancel_emails = [m for m in mail.outbox if 'has been cancelled' in m.subject]
        self.assertEqual(len(cancel_emails), 1)
        self.assertIn('jane@example.com', cancel_emails[0].to)

    def test_no_cancellation_email_attempted_without_a_customer_email_on_file(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING, customer_email='')
        mail.outbox = []
        self.client.post(f'/api/bookings/{booking.id}/cancel/')
        self.assertEqual(len(mail.outbox), 0)


class ChangeDatesActionTests(APITestCase):
    """Adjusting dates in place instead of cancel-and-rebook - see Booking.change_dates."""

    def setUp(self):
        self.user = User.objects.create_user(username='jane@example.com', password='pass12345!', email='jane@example.com')
        self.vehicle = make_vehicle()  # price_per_day=1000
        self.client.force_authenticate(user=self.user)

    def test_customer_can_change_dates_of_a_pending_booking(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        new_start, new_end = TOMORROW + timedelta(days=2), TOMORROW + timedelta(days=4)
        response = self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(new_start), 'end_date': str(new_end)},
        )
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.start_date, new_start)
        self.assertEqual(booking.end_date, new_end)
        self.assertEqual(booking.status, BookingStatus.PENDING)

    def test_changing_dates_recomputes_the_total_for_the_new_trip_length(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)  # 7 days -> 7000
        new_start = TOMORROW
        new_end = TOMORROW + timedelta(days=2)  # 3 days -> 3000
        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(new_start), 'end_date': str(new_end)},
        )
        booking.refresh_from_db()
        self.assertEqual(booking.total_amount, Decimal('3000.00'))

    def test_confirmed_booking_stays_confirmed_after_an_extension_even_if_deposit_no_longer_covers_30_percent(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.CONFIRMED)  # 7000 total
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=Decimal('2100'), status=PaymentStatus.SUCCESSFUL,
        )  # exactly the old 30% deposit
        new_start, new_end = TOMORROW, TOMORROW + timedelta(days=20)  # much longer trip -> much bigger total
        response = self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(new_start), 'end_date': str(new_end)},
        )
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)
        self.assertGreater(booking.balance_due, 0)

    def test_shortening_a_fully_paid_trip_creates_a_refund_for_the_overpayment(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.CONFIRMED)  # 7000 total
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=Decimal('7000'), status=PaymentStatus.SUCCESSFUL,
        )
        new_start = TOMORROW
        new_end = TOMORROW + timedelta(days=1)  # 2 days -> 2000, so 5000 overpaid
        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(new_start), 'end_date': str(new_end)},
        )
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, Decimal('5000.00'))
        self.assertEqual(refund.status, 'pending')

    def test_changing_dates_again_updates_an_existing_pending_refund_instead_of_duplicating(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.CONFIRMED)  # 7000 total
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=Decimal('7000'), status=PaymentStatus.SUCCESSFUL,
        )
        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TOMORROW), 'end_date': str(TOMORROW + timedelta(days=1))},  # 2000 -> 5000 overpaid
        )
        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TOMORROW), 'end_date': str(TOMORROW)},  # 1000 -> 6000 overpaid
        )
        self.assertEqual(Refund.objects.filter(booking=booking).count(), 1)
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, Decimal('6000.00'))

    def test_changing_dates_back_up_removes_a_now_stale_pending_refund(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.CONFIRMED)  # 7000 total
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=Decimal('7000'), status=PaymentStatus.SUCCESSFUL,
        )
        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TOMORROW), 'end_date': str(TOMORROW + timedelta(days=1))},  # overpaid by 5000
        )
        self.assertTrue(Refund.objects.filter(booking=booking).exists())

        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TOMORROW), 'end_date': str(TOMORROW + timedelta(days=9))},  # 10 days -> 10000, no longer overpaid
        )
        self.assertFalse(Refund.objects.filter(booking=booking).exists())

    def test_cannot_change_dates_to_a_range_that_conflicts_with_another_booking(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        blocking_start, blocking_end = TOMORROW + timedelta(days=30), TOMORROW + timedelta(days=35)
        make_booking(self.user, self.vehicle, status=BookingStatus.CONFIRMED, start_date=blocking_start, end_date=blocking_end)

        response = self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(blocking_start), 'end_date': str(blocking_end)},
        )
        self.assertEqual(response.status_code, 400)
        booking.refresh_from_db()
        self.assertEqual(booking.start_date, TOMORROW)

    def test_cannot_change_start_date_into_the_past(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TODAY - timedelta(days=1)), 'end_date': str(NEXT_WEEK)},
        )
        self.assertEqual(response.status_code, 400)

    def test_end_date_before_start_date_is_rejected(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(NEXT_WEEK), 'end_date': str(TOMORROW)},
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_change_dates_of_a_cancelled_booking(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.CANCELLED)
        response = self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TOMORROW), 'end_date': str(NEXT_WEEK)},
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_change_dates_of_a_completed_booking(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.COMPLETED)
        response = self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TOMORROW), 'end_date': str(NEXT_WEEK)},
        )
        self.assertEqual(response.status_code, 400)

    def test_customer_cannot_change_dates_on_someone_elses_booking(self):
        other_user = User.objects.create_user(username='other@example.com', password='pass12345!')
        booking = make_booking(other_user, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TOMORROW), 'end_date': str(NEXT_WEEK)},
        )
        self.assertEqual(response.status_code, 404)

    def test_changing_dates_emails_the_customer(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING, customer_email='jane@example.com')
        mail.outbox = []
        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(TOMORROW + timedelta(days=2)), 'end_date': str(TOMORROW + timedelta(days=4))},
        )
        dates_changed_emails = [m for m in mail.outbox if 'dates updated' in m.subject]
        self.assertEqual(len(dates_changed_emails), 1)
        self.assertIn('jane@example.com', dates_changed_emails[0].to)


class DiscountCodeBookingTests(APITestCase):
    """A discount code (see discounts.DiscountCode) reduces total_amount at booking creation,
    before the 30% deposit is calculated off the already-discounted total - see Booking.save()."""

    def setUp(self):
        self.user = User.objects.create_user(username='jane-disc@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))  # 7 days -> 7000
        self.client.force_authenticate(user=self.user)

    def _payload(self, **overrides):
        payload = {
            'vehicle': self.vehicle.id, 'service_type': 'with_driver',
            'customer_name': 'Jane Doe', 'customer_phone': '254700000000',
            'pickup_location': 'Kisumu', 'start_date': str(TOMORROW), 'end_date': str(NEXT_WEEK),
        }
        payload.update(overrides)
        return payload

    def test_a_fixed_discount_code_reduces_the_total(self):
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='SAVE1000', discount_type='fixed', value=Decimal('1000'))
        response = self.client.post('/api/bookings/', self._payload(discount_code='save1000'), format='json')
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('6000.00'))
        self.assertEqual(booking.discount_amount, Decimal('1000.00'))
        self.assertEqual(booking.discount_code.code, 'SAVE1000')

    def test_a_percentage_discount_code_reduces_the_total(self):
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='TENOFF', discount_type='percent', value=Decimal('10'))
        response = self.client.post('/api/bookings/', self._payload(discount_code='TENOFF'), format='json')
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('6300.00'))
        self.assertEqual(booking.discount_amount, Decimal('700.00'))

    def test_the_deposit_is_calculated_off_the_already_discounted_total(self):
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='HALFOFF', discount_type='percent', value=Decimal('50'))
        response = self.client.post('/api/bookings/', self._payload(discount_code='HALFOFF'), format='json')
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('3500.00'))
        self.assertEqual(booking.deposit_amount, Decimal('1050.00'))  # 30% of 3500

    def test_the_code_is_marked_redeemed_and_tied_to_the_booking(self):
        from discounts.models import DiscountCode

        code = DiscountCode.objects.create(code='ONCE', value=Decimal('500'))
        response = self.client.post('/api/bookings/', self._payload(discount_code='ONCE'), format='json')
        booking_id = response.json()['id']
        code.refresh_from_db()
        self.assertTrue(code.is_redeemed)
        self.assertIsNotNone(code.redeemed_at)
        self.assertEqual(code.redeemed_booking_id, booking_id)

    def test_an_already_redeemed_code_cannot_be_used_again(self):
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='SPENT', value=Decimal('500'), is_redeemed=True)
        response = self.client.post('/api/bookings/', self._payload(discount_code='SPENT'), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('discount_code', response.json())
        self.assertEqual(Booking.objects.count(), 0)

    def test_an_inactive_code_cannot_be_used(self):
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='RETIRED', value=Decimal('500'), is_active=False)
        response = self.client.post('/api/bookings/', self._payload(discount_code='RETIRED'), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_an_unknown_code_cannot_be_used(self):
        response = self.client.post('/api/bookings/', self._payload(discount_code='NOSUCHCODE'), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_a_blank_discount_code_is_simply_ignored(self):
        response = self.client.post('/api/bookings/', self._payload(discount_code=''), format='json')
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('7000.00'))
        self.assertEqual(booking.discount_amount, Decimal('0'))
        self.assertIsNone(booking.discount_code)

    def test_a_fixed_discount_larger_than_the_total_just_zeroes_it_out(self):
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='HUGE', discount_type='fixed', value=Decimal('99999'))
        response = self.client.post('/api/bookings/', self._payload(discount_code='HUGE'), format='json')
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('0.00'))

    def test_a_discount_code_cannot_be_applied_through_a_plain_update(self):
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='LATE', value=Decimal('500'))
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.patch(f'/api/bookings/{booking.id}/', {'discount_code': 'LATE'}, format='json')
        self.assertEqual(response.status_code, 400)
        booking.refresh_from_db()
        self.assertIsNone(booking.discount_code)

    def test_changing_dates_reapplies_the_same_discount_to_the_new_total(self):
        from discounts.models import DiscountCode

        code = DiscountCode.objects.create(code='STAYSON', discount_type='percent', value=Decimal('10'))
        response = self.client.post('/api/bookings/', self._payload(discount_code='STAYSON'), format='json')
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('6300.00'))  # 7000 - 10%

        new_start, new_end = TOMORROW, TOMORROW + timedelta(days=1)  # 2 days -> 2000
        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(new_start), 'end_date': str(new_end)},
        )
        booking.refresh_from_db()
        self.assertEqual(booking.total_amount, Decimal('1800.00'))  # 2000 - 10%
        self.assertEqual(booking.discount_amount, Decimal('200.00'))
        # Single-use code isn't re-consumed by a later date change - it's still tied to the
        # same one booking it was originally redeemed against.
        code.refresh_from_db()
        self.assertEqual(code.redeemed_booking_id, booking.id)


class LoyaltyDiscountBookingTests(APITestCase):
    """A customer's own loyalty tier (see accounts.LoyaltyTier) reduces total_amount
    automatically at booking creation - no code needed, unlike discounts.DiscountCode, and
    stacks with one if the customer also has a discount code."""

    def setUp(self):
        from accounts.models import LoyaltyTier

        self.user = User.objects.create_user(username='jane-loyalty@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))  # 7 days -> 7000
        self.client.force_authenticate(user=self.user)
        LoyaltyTier.objects.all().delete()  # ignore the migration-seeded defaults
        self.silver = LoyaltyTier.objects.create(name='Silver', min_completed_trips=1, discount_percent=Decimal('10'))

    def _payload(self, **overrides):
        payload = {
            'vehicle': self.vehicle.id, 'service_type': 'with_driver',
            'customer_name': 'Jane Doe', 'customer_phone': '254700000000',
            'pickup_location': 'Kisumu', 'start_date': str(TOMORROW), 'end_date': str(NEXT_WEEK),
        }
        payload.update(overrides)
        return payload

    def test_no_discount_below_the_lowest_tier_threshold(self):
        response = self.client.post('/api/bookings/', self._payload(), format='json')
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('7000.00'))
        self.assertEqual(booking.loyalty_discount_amount, Decimal('0'))

    def test_discount_applies_once_the_tier_is_reached(self):
        make_booking(self.user, self.vehicle, status=BookingStatus.COMPLETED)
        response = self.client.post('/api/bookings/', self._payload(), format='json')
        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('6300.00'))  # 7000 - 10%
        self.assertEqual(booking.loyalty_discount_amount, Decimal('700.00'))

    def test_the_deposit_is_calculated_off_the_loyalty_discounted_total(self):
        make_booking(self.user, self.vehicle, status=BookingStatus.COMPLETED)
        response = self.client.post('/api/bookings/', self._payload(), format='json')
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.deposit_amount, Decimal('1890.00'))  # 30% of 6300

    def test_stacks_with_a_discount_code_applied_sequentially(self):
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='SAVE1000', discount_type='fixed', value=Decimal('1000'))
        make_booking(self.user, self.vehicle, status=BookingStatus.COMPLETED)
        response = self.client.post('/api/bookings/', self._payload(discount_code='SAVE1000'), format='json')
        booking = Booking.objects.get(pk=response.json()['id'])
        # 7000 - 1000 (code) = 6000, then -10% loyalty = 5400
        self.assertEqual(booking.discount_amount, Decimal('1000.00'))
        self.assertEqual(booking.loyalty_discount_amount, Decimal('600.00'))
        self.assertEqual(booking.total_amount, Decimal('5400.00'))

    def test_someone_elses_completed_trips_dont_count(self):
        other_user = User.objects.create_user(username='not-jane@example.com', password='pass12345!')
        make_booking(other_user, self.vehicle, status=BookingStatus.COMPLETED)
        response = self.client.post('/api/bookings/', self._payload(), format='json')
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.loyalty_discount_amount, Decimal('0'))

    def test_changing_dates_reapplies_the_loyalty_discount_to_the_new_total(self):
        make_booking(self.user, self.vehicle, status=BookingStatus.COMPLETED)
        response = self.client.post('/api/bookings/', self._payload(), format='json')
        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertEqual(booking.total_amount, Decimal('6300.00'))  # 7000 - 10%

        new_start, new_end = TOMORROW, TOMORROW + timedelta(days=1)  # 2 days -> 2000
        self.client.post(
            f'/api/bookings/{booking.id}/change_dates/',
            {'start_date': str(new_start), 'end_date': str(new_end)},
        )
        booking.refresh_from_db()
        self.assertEqual(booking.total_amount, Decimal('1800.00'))  # 2000 - 10%
        self.assertEqual(booking.loyalty_discount_amount, Decimal('200.00'))


class DiscountCodeRaceConditionTests(TransactionTestCase):
    """Proves two concurrent bookings can't both redeem the same single-use code - mirrors
    BookingRaceConditionTests below, using the same slow-down-the-window-and-race-two-real-
    threads technique (a single-connection test can't reproduce a genuine race)."""

    def setUp(self):
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.user_a = User.objects.create_user(username='disc-race-a@example.com', password='pass12345!')
        self.user_b = User.objects.create_user(username='disc-race-b@example.com', password='pass12345!')
        from discounts.models import DiscountCode

        DiscountCode.objects.create(code='RACEME', value=Decimal('100'))

    def _payload(self, start, end):
        return {
            'vehicle': self.vehicle.id, 'service_type': 'with_driver',
            'customer_name': 'Racer', 'customer_phone': '254700000000',
            'pickup_location': 'Kisumu', 'start_date': str(start), 'end_date': str(end),
            'discount_code': 'RACEME',
        }

    def test_two_concurrent_bookings_cant_both_redeem_the_same_code(self):
        from discounts.services import reserve_code

        original_reserve_code = reserve_code

        def slow_reserve_code(code_str):
            result = original_reserve_code(code_str)
            time.sleep(0.3)
            return result

        results = {}

        def attempt(user, key, start, end):
            client = APIClient()
            client.force_authenticate(user=user)
            response = client.post('/api/bookings/', self._payload(start, end), format='json')
            results[key] = response.status_code
            connection.close()

        # Different, non-conflicting date ranges - only the shared discount code should be
        # contested here, not the vehicle itself.
        with patch('bookings.serializers.reserve_code', side_effect=slow_reserve_code):
            t1 = threading.Thread(target=attempt, args=(self.user_a, 'a', TOMORROW, NEXT_WEEK))
            t2 = threading.Thread(
                target=attempt, args=(self.user_b, 'b', TOMORROW + timedelta(days=30), TOMORROW + timedelta(days=35)),
            )
            t1.start()
            time.sleep(0.05)
            t2.start()
            t1.join()
            t2.join()

        # Whichever thread loses gets either a clean 400 (its own reserve_code call saw the
        # code already redeemed) or a 409 (it hit the *vehicle* lock - both requests touch the
        # same vehicle row first - and gave up rather than waiting forever); either way, exactly
        # one booking ever actually redeems the code. See BookingRaceConditionTests above for
        # the same two-outcomes-for-the-loser reasoning.
        statuses = sorted(results.values())
        self.assertEqual(len(statuses), 2, f'expected both requests to get a response, got {results}')
        self.assertEqual(statuses.count(201), 1, f'expected exactly one booking to redeem the code, got {results}')
        self.assertIn(statuses[0] if statuses[1] == 201 else statuses[1], (400, 409))

        from discounts.models import DiscountCode

        self.assertTrue(DiscountCode.objects.get(code='RACEME').is_redeemed)
        self.assertEqual(Booking.objects.filter(discount_code__code='RACEME').count(), 1)


class WaitlistNotificationTests(APITestCase):
    """Cancelling a booking should tell anyone waitlisted for a date range that overlapped it -
    but only once that range genuinely has no other blocking booking left covering it, and only
    once ever per entry. See Booking.mark_cancelled -> bookings.services.notify_waitlist_for_freed_dates."""

    def setUp(self):
        self.vehicle = make_vehicle()
        self.owner = User.objects.create_user(username='owner@example.com', password='pass12345!')
        self.waiter = User.objects.create_user(
            username='waiter@example.com', password='pass12345!', first_name='Wanjiru',
            email='waiter@example.com',
        )

    def test_cancelling_the_only_blocking_booking_notifies_and_emails_the_waiter(self):
        from .models import WaitlistEntry

        booking = make_booking(self.owner, self.vehicle, status=BookingStatus.PENDING)
        entry = WaitlistEntry.objects.create(
            vehicle=self.vehicle, user=self.waiter, start_date=booking.start_date, end_date=booking.end_date,
        )
        mail.outbox = []

        booking.mark_cancelled()

        entry.refresh_from_db()
        self.assertIsNotNone(entry.notified_at)
        waitlist_emails = [m for m in mail.outbox if 'is now available' in m.subject]
        self.assertEqual(len(waitlist_emails), 1)
        self.assertIn('waiter@example.com', waitlist_emails[0].to)

    def test_not_notified_if_a_different_booking_still_blocks_the_range(self):
        from .models import WaitlistEntry

        booking_a = make_booking(self.owner, self.vehicle, status=BookingStatus.PENDING)
        make_booking(
            self.owner, self.vehicle, status=BookingStatus.CONFIRMED,
            start_date=booking_a.start_date, end_date=booking_a.end_date,
        )
        entry = WaitlistEntry.objects.create(
            vehicle=self.vehicle, user=self.waiter, start_date=booking_a.start_date, end_date=booking_a.end_date,
        )
        mail.outbox = []

        booking_a.mark_cancelled()

        entry.refresh_from_db()
        self.assertIsNone(entry.notified_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_an_already_notified_entry_is_not_notified_again(self):
        from .models import WaitlistEntry

        booking = make_booking(self.owner, self.vehicle, status=BookingStatus.PENDING)
        original_notified_at = timezone.now() - timedelta(days=1)
        entry = WaitlistEntry.objects.create(
            vehicle=self.vehicle, user=self.waiter, start_date=booking.start_date, end_date=booking.end_date,
            notified_at=original_notified_at,
        )
        mail.outbox = []

        booking.mark_cancelled()

        self.assertEqual(len(mail.outbox), 0)
        entry.refresh_from_db()
        self.assertEqual(entry.notified_at, original_notified_at)

    def test_entry_for_a_non_overlapping_date_range_is_not_notified(self):
        from .models import WaitlistEntry

        booking = make_booking(self.owner, self.vehicle, status=BookingStatus.PENDING)
        entry = WaitlistEntry.objects.create(
            vehicle=self.vehicle, user=self.waiter,
            start_date=booking.end_date + timedelta(days=30), end_date=booking.end_date + timedelta(days=37),
        )
        mail.outbox = []

        booking.mark_cancelled()

        entry.refresh_from_db()
        self.assertIsNone(entry.notified_at)
        self.assertEqual(len(mail.outbox), 0)


class BookForSomeoneElseEmailTests(APITestCase):
    """When customer_name/phone/email describe a different rider than the account holder (e.g.
    booking a ride for a family member), both people should hear about it - the rider gets trip
    details, and the account holder (who actually paid) gets their own copy too."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='payer@example.com', password='pass12345!', email='payer@example.com', first_name='Mark',
        )
        self.vehicle = make_vehicle()

    def test_confirming_a_booking_made_for_someone_else_emails_both_people(self):
        booking = make_booking(
            self.user, self.vehicle, status=BookingStatus.PENDING,
            customer_name='Jane Rider', customer_email='jane.rider@example.com',
        )
        mail.outbox = []
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()

        confirmation_emails = [m for m in mail.outbox if 'Booking Confirmed' in m.subject]
        self.assertEqual(len(confirmation_emails), 2)
        recipients = {recipient for m in confirmation_emails for recipient in m.to}
        self.assertEqual(recipients, {'jane.rider@example.com', 'payer@example.com'})

    def test_confirming_a_booking_for_yourself_only_sends_one_email(self):
        booking = make_booking(
            self.user, self.vehicle, status=BookingStatus.PENDING,
            customer_name='Mark Payer', customer_email='payer@example.com',
        )
        mail.outbox = []
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()

        confirmation_emails = [m for m in mail.outbox if 'Booking Confirmed' in m.subject]
        self.assertEqual(len(confirmation_emails), 1)

    def test_cancelling_a_booking_made_for_someone_else_emails_both_people(self):
        booking = make_booking(
            self.user, self.vehicle, status=BookingStatus.PENDING,
            customer_name='Jane Rider', customer_email='jane.rider@example.com',
        )
        mail.outbox = []
        self.client.force_authenticate(user=self.user)
        self.client.post(f'/api/bookings/{booking.id}/cancel/')

        cancel_emails = [m for m in mail.outbox if 'has been cancelled' in m.subject]
        self.assertEqual(len(cancel_emails), 2)
        recipients = {recipient for m in cancel_emails for recipient in m.to}
        self.assertEqual(recipients, {'jane.rider@example.com', 'payer@example.com'})


class CancellationRefundPercentageTests(APITestCase):
    """A client cancelling before the driver has actually committed to the trip (or a self-drive
    booking, which has no driver-commitment concept at all) gets everything back. Once the
    driver has acknowledged the booking, a client cancelling themselves only gets half back -
    unless staff attest the driver was actually at fault (went unavailable, or delayed without
    telling anyone), in which case it's still a full refund regardless of acknowledgment."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Refund Policy Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='refund-policy-client@example.com', password='pass12345!')

    def _paid_booking(self, **kwargs):
        booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING, **kwargs)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        return booking

    def test_client_cancelling_before_driver_acknowledgment_gets_a_full_refund(self):
        booking = self._paid_booking()
        self.assertIsNone(booking.driver_acknowledged_at)
        booking.mark_cancelled()
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, booking.total_amount)

    def test_cancelling_notifies_admins_the_driver_and_the_client_in_app(self):
        from notifications.models import Notification, NotificationEvent

        booking = self._paid_booking()
        booking.mark_cancelled()

        notifications = Notification.objects.filter(event=NotificationEvent.BOOKING_CANCELLED)
        self.assertEqual(notifications.count(), 3)
        admin_notification = notifications.get(driver__isnull=True, user__isnull=True)
        driver_notification = notifications.get(driver_id=self.driver.id)
        client_notification = notifications.get(user_id=self.customer.id)
        self.assertIn(str(booking.id), admin_notification.message)
        self.assertIn(str(booking.id), driver_notification.message)
        self.assertIn(str(booking.id), client_notification.message)
        self.assertEqual(driver_notification.link_path, '/driver')
        self.assertEqual(client_notification.link_path, '/account/bookings')

    def test_client_cancelling_after_driver_acknowledgment_gets_half_refunded(self):
        booking = self._paid_booking()
        booking.driver_acknowledged_at = timezone.now()
        booking.save(update_fields=['driver_acknowledged_at'])

        booking.mark_cancelled()
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, (booking.total_amount / 2).quantize(Decimal('0.01')))

    def test_staff_flagging_driver_at_fault_forces_a_full_refund_even_after_acknowledgment(self):
        booking = self._paid_booking()
        booking.driver_acknowledged_at = timezone.now()
        booking.save(update_fields=['driver_acknowledged_at'])

        booking.mark_cancelled(driver_at_fault=True)
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, booking.total_amount)

    def test_self_drive_booking_always_gets_a_full_refund(self):
        self_drive_vehicle = make_vehicle(name='Refund Policy Self Drive Car', price_per_day=Decimal('1000'))
        booking = make_booking(
            self.customer, self_drive_vehicle, status=BookingStatus.PENDING, service_type=ServiceType.SELF_DRIVE,
            customer_license_document=SimpleUploadedFile('license.pdf', b'x', content_type='application/pdf'),
            customer_id_document=SimpleUploadedFile('id.pdf', b'x', content_type='application/pdf'),
        )
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.mark_cancelled()
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, booking.total_amount)

    def test_a_late_payment_after_a_half_refund_cancellation_only_tops_up_to_half(self):
        booking = self._paid_booking()  # KES 7000 paid so far, out of a 7000 total
        booking.driver_acknowledged_at = timezone.now()
        booking.save(update_fields=['driver_acknowledged_at'])
        booking.mark_cancelled()
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, Decimal('3500.00'))

        # A second, already-in-flight payment lands after cancellation (simulating a delayed
        # STK push) - the refund should only top up to half of the new total paid, not all of it.
        Payment.objects.create(
            booking=booking, method=PaymentMethod.MPESA, amount=Decimal('1000'), status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()

        refund.refresh_from_db()
        self.assertEqual(refund.amount, Decimal('4000.00'))  # half of 8000

    def test_customer_cannot_self_flag_driver_at_fault(self):
        booking = self._paid_booking()
        booking.driver_acknowledged_at = timezone.now()
        booking.save(update_fields=['driver_acknowledged_at'])

        self.client.force_authenticate(user=self.customer)
        response = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'driver_at_fault': True}, format='json')
        self.assertEqual(response.status_code, 200)
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, (booking.total_amount / 2).quantize(Decimal('0.01')))

    def test_staff_can_flag_driver_at_fault_via_the_general_cancel_endpoint(self):
        booking = self._paid_booking()
        booking.driver_acknowledged_at = timezone.now()
        booking.save(update_fields=['driver_acknowledged_at'])

        staff = User.objects.create_user(username='refund-policy-staff@example.com', password='pass12345!', is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.post(f'/api/bookings/{booking.id}/cancel/', {'driver_at_fault': True}, format='json')
        self.assertEqual(response.status_code, 200)
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, booking.total_amount)

    def test_staff_can_flag_driver_at_fault_via_the_admin_set_status_endpoint(self):
        booking = self._paid_booking()
        booking.driver_acknowledged_at = timezone.now()
        booking.save(update_fields=['driver_acknowledged_at'])

        staff = User.objects.create_user(username='refund-policy-admin@example.com', password='pass12345!', is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.post(
            f'/api/admin/bookings/{booking.id}/set-status/',
            {'status': 'cancelled', 'driver_at_fault': True}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        refund = Refund.objects.get(booking=booking)
        self.assertEqual(refund.amount, booking.total_amount)


class BookingReviewActionTests(APITestCase):
    """Covers /api/bookings/<id>/review/ - a customer reviewing their own completed trip."""

    def setUp(self):
        self.user = User.objects.create_user(username='jane@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Driver One', is_active=True)
        self.vehicle = make_vehicle()
        self.client.force_authenticate(user=self.user)

    def test_cannot_review_before_trip_is_completed(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED)
        response = self.client.post(f'/api/bookings/{booking.id}/review/', {'rating': 5, 'comment': 'Great!'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Review.objects.filter(booking=booking).exists())

    def test_can_review_a_completed_trip_and_it_links_to_the_driver(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver, status=BookingStatus.COMPLETED)
        response = self.client.post(f'/api/bookings/{booking.id}/review/', {'rating': 5, 'comment': 'Great driver!'})
        self.assertEqual(response.status_code, 201)

        review = Review.objects.get(booking=booking)
        self.assertEqual(review.driver_id, self.driver.id)
        self.assertEqual(review.customer_name, booking.customer_name)
        self.assertFalse(review.is_approved)  # still needs admin moderation

    def test_cannot_review_the_same_trip_twice(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver, status=BookingStatus.COMPLETED)
        first = self.client.post(f'/api/bookings/{booking.id}/review/', {'rating': 5, 'comment': 'Great!'})
        self.assertEqual(first.status_code, 201)

        second = self.client.post(f'/api/bookings/{booking.id}/review/', {'rating': 1, 'comment': 'Changed my mind'})
        self.assertEqual(second.status_code, 400)
        self.assertEqual(Review.objects.filter(booking=booking).count(), 1)

    def test_rating_must_be_between_1_and_5(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver, status=BookingStatus.COMPLETED)
        response = self.client.post(f'/api/bookings/{booking.id}/review/', {'rating': 6, 'comment': 'Too high'})
        self.assertEqual(response.status_code, 400)


class DriverOnsiteBookingCreateTests(APITestCase):
    """Covers /api/driver/bookings/create/ - a driver booking a walk-up client on the spot."""

    def setUp(self):
        driver_user = User.objects.create_user(username='onsite-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Onsite Driver', is_active=True)
        self.own_vehicle = make_vehicle(name='My Car', driver=self.driver)
        self.other_driver = Driver.objects.create(full_name='Other Driver', is_active=True)
        self.other_vehicle = make_vehicle(name='Someone Elses Car', driver=self.other_driver)
        self.client.force_authenticate(user=driver_user)

    def _payload(self, **overrides):
        payload = dict(
            vehicle=self.own_vehicle.id, customer_name='Walk Up Client', customer_phone='254711111111',
            pickup_location='Kisumu Airport', start_date=str(TOMORROW), end_date=str(NEXT_WEEK),
        )
        payload.update(overrides)
        return payload

    def test_driver_can_create_a_booking_for_their_own_vehicle(self):
        response = self.client.post('/api/driver/bookings/create/', self._payload(), format='json')
        self.assertEqual(response.status_code, 201)

        booking = Booking.objects.get(pk=response.json()['booking']['id'])
        self.assertEqual(booking.driver_id, self.driver.id)
        self.assertEqual(booking.source, BookingSource.DRIVER_ONSITE)
        self.assertEqual(booking.service_type, ServiceType.WITH_DRIVER)
        self.assertIn(str(booking.customer_token), response.json()['payment_url'])

    def test_a_walk_in_booking_is_confirmed_immediately_with_no_deposit_required(self):
        # Unlike an online booking (Pending until a 30% deposit lands), a walk-in client is
        # standing right there with the driver, so there's no remote-trust problem to solve -
        # full payment is typically only collected once the trip itself is over.
        response = self.client.post('/api/driver/bookings/create/', self._payload(), format='json')
        booking = Booking.objects.get(pk=response.json()['booking']['id'])
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)
        self.assertEqual(booking.amount_paid, Decimal('0'))

    def test_a_walk_in_booking_can_start_its_trip_immediately_with_no_payment(self):
        response = self.client.post('/api/driver/bookings/create/', self._payload(), format='json')
        booking_id = response.json()['booking']['id']

        start_response = self.client.post(f'/api/driver/bookings/{booking_id}/start-trip/')
        self.assertEqual(start_response.status_code, 200)

    def test_malformed_customer_phone_is_rejected(self):
        response = self.client.post(
            '/api/driver/bookings/create/', self._payload(customer_phone='0711111111'), format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('customer_phone', response.json())

    def test_driver_cannot_book_a_vehicle_that_isnt_theirs(self):
        response = self.client.post(
            '/api/driver/bookings/create/', self._payload(vehicle=self.other_vehicle.id), format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Booking.objects.filter(vehicle=self.other_vehicle).exists())

    def test_conflicting_dates_on_the_same_vehicle_are_rejected(self):
        make_booking(
            User.objects.create_user(username='existing@example.com', password='pass12345!'),
            self.own_vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
        )
        response = self.client.post('/api/driver/bookings/create/', self._payload(), format='json')
        self.assertEqual(response.status_code, 400)

    def test_repeat_walk_up_client_with_same_phone_reuses_their_account(self):
        first = self.client.post('/api/driver/bookings/create/', self._payload(), format='json')
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            '/api/driver/bookings/create/',
            self._payload(start_date=str(NEXT_WEEK + timedelta(days=1)), end_date=str(NEXT_WEEK + timedelta(days=3))),
            format='json',
        )
        self.assertEqual(second.status_code, 201)

        first_booking = Booking.objects.get(pk=first.json()['booking']['id'])
        second_booking = Booking.objects.get(pk=second.json()['booking']['id'])
        self.assertEqual(first_booking.user_id, second_booking.user_id)


class DriverDeclarePaymentTests(APITestCase):
    """A driver, with the client physically present, declaring exactly how much the client says
    they're paying and by which method. Cash/card create a pending payment awaiting the driver's
    confirmation (see DriverConfirmPaymentTests); M-Pesa triggers the existing STK Push flow
    immediately against the client's own phone."""

    def setUp(self):
        driver_user = User.objects.create_user(username='declare-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(
            user=driver_user, full_name='Declare Driver', is_active=True, cash_payments_enabled=True,
        )
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='client@example.com', password='pass12345!')
        self.booking = make_booking(
            self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING,
            customer_phone='254700000000',
        )
        self.client.force_authenticate(user=driver_user)

    def _url(self):
        return f'/api/driver/bookings/{self.booking.id}/declare-payment/'

    def test_driver_can_declare_a_cash_payment(self):
        response = self.client.post(
            self._url(), {'method': 'cash', 'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.method, PaymentMethod.CASH)
        self.assertEqual(payment.status, PaymentStatus.PENDING)  # not collected yet, just declared
        self.assertEqual(payment.recorded_by_driver_id, self.driver.id)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.PENDING)  # unconfirmed until actually received

    def test_driver_can_declare_a_card_payment(self):
        response = self.client.post(
            self._url(), {'method': 'card', 'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.method, PaymentMethod.CARD)
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_declaring_mpesa_triggers_an_stk_push_to_the_clients_phone(self, mock_stk):
        mock_stk.return_value = {'CheckoutRequestID': 'ws_CO_1'}
        response = self.client.post(
            self._url(), {'method': 'mpesa', 'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        mock_stk.assert_called_once()
        self.assertEqual(mock_stk.call_args.kwargs['phone_number'], '254700000000')

        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.method, PaymentMethod.MPESA)
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    def test_cannot_declare_cash_when_disabled_for_this_driver(self):
        self.driver.cash_payments_enabled = False
        self.driver.save(update_fields=['cash_payments_enabled'])

        response = self.client.post(
            self._url(), {'method': 'cash', 'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_can_still_declare_card_when_cash_is_disabled(self):
        self.driver.cash_payments_enabled = False
        self.driver.save(update_fields=['cash_payments_enabled'])

        response = self.client.post(
            self._url(), {'method': 'card', 'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_cannot_declare_for_another_drivers_booking(self):
        other_driver_user = User.objects.create_user(username='other-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Not This Driver', is_active=True)
        self.client.force_authenticate(user=other_driver_user)

        response = self.client.post(self._url(), {'method': 'cash', 'amount': '100'}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_cannot_declare_an_amount_exceeding_the_balance_due(self):
        response = self.client.post(
            self._url(), {'method': 'cash', 'amount': str(self.booking.total_amount + 1)}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_cannot_declare_a_zero_or_negative_amount(self):
        for bad_amount in ('0', '-500'):
            response = self.client.post(self._url(), {'method': 'cash', 'amount': bad_amount}, format='json')
            self.assertEqual(response.status_code, 400, f'amount={bad_amount} should have been rejected')
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_cannot_declare_against_a_cancelled_booking(self):
        self.booking.status = BookingStatus.CANCELLED
        self.booking.save(update_fields=['status'])

        response = self.client.post(
            self._url(), {'method': 'cash', 'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_invalid_method_is_rejected(self):
        response = self.client.post(self._url(), {'method': 'bitcoin', 'amount': '100'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_non_numeric_amount_is_rejected(self):
        response = self.client.post(self._url(), {'method': 'cash', 'amount': 'abc'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_driver_can_declare_a_bank_transfer_with_a_reference(self):
        response = self.client.post(
            self._url(),
            {'method': 'bank_transfer', 'amount': str(self.booking.deposit_amount), 'reference': 'QGH7XXXXXX'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.method, PaymentMethod.BANK_TRANSFER)
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertEqual(payment.note, 'QGH7XXXXXX')

    def test_cannot_declare_a_bank_transfer_without_a_reference(self):
        response = self.client.post(
            self._url(), {'method': 'bank_transfer', 'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_cannot_declare_a_bank_transfer_with_a_reference_shorter_than_4_characters(self):
        response = self.client.post(
            self._url(),
            {'method': 'bank_transfer', 'amount': str(self.booking.deposit_amount), 'reference': 'abc'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_amount_is_stored_as_an_exact_decimal_not_a_float(self):
        # Parsed via core.utils.parse_amount rather than float() - this specific value has a
        # well-known binary floating-point representation error (0.1 can't be represented
        # exactly), so if float() ever crept back in, this would be the case to catch it on.
        response = self.client.post(self._url(), {'method': 'cash', 'amount': '2333.10'}, format='json')
        self.assertEqual(response.status_code, 200)
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.amount, Decimal('2333.10'))

    def _results(self, response):
        data = response.json()
        return data['results'] if 'results' in data else data

    def test_booking_lists_a_declared_cash_payment_as_pending_until_confirmed(self):
        self.client.post(self._url(), {'method': 'cash', 'amount': str(self.booking.deposit_amount)}, format='json')
        payment = Payment.objects.get(booking=self.booking)

        response = self.client.get('/api/driver/bookings/mine/')
        pending = next(b for b in self._results(response) if b['id'] == self.booking.id)['pending_payments']
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['id'], payment.id)
        self.assertEqual(pending[0]['method'], 'cash')

        self.client.post(f'/api/driver/payments/{payment.id}/confirm/')
        response = self.client.get('/api/driver/bookings/mine/')
        pending = next(b for b in self._results(response) if b['id'] == self.booking.id)['pending_payments']
        self.assertEqual(len(pending), 0)


class DriverConfirmPaymentTests(APITestCase):
    """A driver confirming a previously-declared cash/card payment was actually received - the
    amount was already locked in at declaration time, so confirming takes no amount at all."""

    def setUp(self):
        driver_user = User.objects.create_user(username='confirm-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Confirm Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='confirm-client@example.com', password='pass12345!')
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING)
        self.payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.PENDING, recorded_by_driver=self.driver,
        )
        self.client.force_authenticate(user=driver_user)

    def _url(self, payment=None):
        return f'/api/driver/payments/{(payment or self.payment).id}/confirm/'

    def test_driver_can_confirm_a_declared_payment(self):
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.SUCCESSFUL)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)  # fully paid -> auto-confirmed

    def test_cannot_confirm_the_same_payment_twice(self):
        self.client.post(self._url())
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 400)

    def test_cannot_confirm_for_another_drivers_payment(self):
        other_driver_user = User.objects.create_user(username='other-confirm-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Not This Driver', is_active=True)
        self.client.force_authenticate(user=other_driver_user)

        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 404)

    def test_cannot_confirm_an_mpesa_payment_this_way(self):
        mpesa_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA, amount=Decimal('100'), status=PaymentStatus.PENDING,
        )
        response = self.client.post(self._url(mpesa_payment))
        self.assertEqual(response.status_code, 400)

    def test_cannot_confirm_a_bank_transfer_payment_this_way(self):
        bank_transfer_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.BANK_TRANSFER, amount=Decimal('100'),
            status=PaymentStatus.PENDING, note='QGH7XXXXXX',
        )
        response = self.client.post(self._url(bank_transfer_payment))
        self.assertEqual(response.status_code, 400)
        self.assertIn('staff', response.json()['detail'].lower())
        bank_transfer_payment.refresh_from_db()
        self.assertEqual(bank_transfer_payment.status, PaymentStatus.PENDING)

    def test_confirming_flags_its_payout_as_needing_verification(self):
        self.client.post(self._url())
        payout = DriverPayout.objects.get(booking=self.booking)
        self.assertTrue(payout.needs_verification)
        self.assertFalse(payout.is_verified)

    def test_mpesa_confirmed_payout_does_not_need_verification(self):
        # Simulate a successful M-Pesa payment (as the callback would record it) instead of
        # cash, for the full amount, so the payout actually gets created.
        self.payment.delete()
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.booking.confirm_if_deposit_met()
        payout = DriverPayout.objects.get(booking=self.booking)
        self.assertFalse(payout.needs_verification)

    def test_confirming_emails_the_customer_as_an_independent_check(self):
        self.booking.customer_email = 'confirm-client@example.com'
        self.booking.save(update_fields=['customer_email'])

        mail.outbox = []
        self.client.post(self._url())
        emails = [m for m in mail.outbox if 'payment recorded' in m.subject]
        self.assertEqual(len(emails), 1)
        self.assertIn(self.booking.customer_email, emails[0].to)

    def test_confirming_also_emails_the_driver_a_confirmation(self):
        self.driver.email = 'confirm-driver@example.com'
        self.driver.save(update_fields=['email'])

        mail.outbox = []
        self.client.post(self._url())
        driver_emails = [m for m in mail.outbox if 'payment recorded' in m.subject and self.driver.email in m.to]
        self.assertEqual(len(driver_emails), 1)

    @patch('notifications.sms.send_sms')
    def test_confirming_sms_the_customer_a_confirmation(self, mock_send_sms):
        self.client.post(self._url())
        mock_send_sms.assert_called_once()
        phone_arg, message_arg = mock_send_sms.call_args[0]
        self.assertEqual(phone_arg, self.booking.customer_phone)
        self.assertIn(str(self.booking.pk), message_arg)

    @patch('notifications.sms.send_sms', side_effect=Exception('gateway down'))
    def test_a_broken_sms_gateway_never_blocks_confirmation(self, mock_send_sms):
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)

    def test_confirming_a_cash_payment_notifies_staff(self):
        staff_user = User.objects.create_user(
            username='confirm-staff@example.com', email='confirm-staff@example.com',
            password='pass12345!', is_staff=True,
        )
        mail.outbox = []
        self.client.post(self._url())
        staff_emails = [m for m in mail.outbox if 'Cash payment recorded' in m.subject]
        self.assertEqual(len(staff_emails), 1)
        self.assertIn(staff_user.email, staff_emails[0].bcc)

    def test_confirming_a_card_payment_does_not_notify_staff(self):
        card_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CARD, amount=self.booking.total_amount,
            status=PaymentStatus.PENDING, recorded_by_driver=self.driver,
        )
        self.payment.delete()
        User.objects.create_user(
            username='confirm-staff2@example.com', email='confirm-staff2@example.com',
            password='pass12345!', is_staff=True,
        )
        mail.outbox = []
        self.client.post(self._url(card_payment))
        self.assertFalse(any('Cash payment recorded' in m.subject for m in mail.outbox))

    def test_confirming_a_cash_payment_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post(self._url())
        self.assertEqual(Notification.objects.filter(event=NotificationEvent.CASH_PAYMENT_RECORDED).count(), 1)

    def test_confirming_notifies_the_client_in_app_for_either_method(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post(self._url())
        notification = Notification.objects.get(event=NotificationEvent.PAYMENT_RECORDED)
        self.assertEqual(notification.user_id, self.customer.id)
        self.assertIn(str(self.booking.id), notification.message)

    def test_confirming_a_card_payment_does_not_notify_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        card_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CARD, amount=self.booking.total_amount,
            status=PaymentStatus.PENDING, recorded_by_driver=self.driver,
        )
        self.payment.delete()
        self.client.post(self._url(card_payment))
        self.assertFalse(Notification.objects.filter(event=NotificationEvent.CASH_PAYMENT_RECORDED).exists())

    def test_no_driver_email_attempted_without_an_email_on_file(self):
        self.assertEqual(self.driver.email, '')
        mail.outbox = []
        self.client.post(self._url())
        driver_emails = [m for m in mail.outbox if self.driver.email and self.driver.email in m.to]
        self.assertEqual(len(driver_emails), 0)

    def test_no_customer_email_attempted_without_one_on_file(self):
        self.assertEqual(self.booking.customer_email, '')
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)


class DriverCashDepositTests(APITestCase):
    """A driver logging that they've deposited cash they collected into the company Paybill -
    the second half of the cash-payment trust chain. The deposited amount can never be less
    than what was collected."""

    def setUp(self):
        driver_user = User.objects.create_user(username='deposit-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Deposit Driver', is_active=True)
        vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='deposit-client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=self.driver, status=BookingStatus.PENDING)
        self.cash_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )
        self.client.force_authenticate(user=driver_user)

    def _url(self, payment=None):
        return f'/api/driver/payments/{(payment or self.cash_payment).id}/deposit/'

    def test_driver_can_log_a_matching_deposit(self):
        response = self.client.post(
            self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': 'QWE1234567'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.cash_payment.refresh_from_db()
        self.assertEqual(self.cash_payment.cash_deposit.amount, self.cash_payment.amount)
        self.assertEqual(self.cash_payment.cash_deposit.mpesa_reference, 'QWE1234567')
        self.assertEqual(self.cash_payment.cash_deposit.logged_by_id, self.driver.id)

    def test_depositing_less_than_collected_is_rejected(self):
        short_amount = self.cash_payment.amount - 1
        response = self.client.post(
            self._url(), {'amount': str(short_amount), 'mpesa_reference': 'QWE1234568'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.cash_payment.refresh_from_db()
        self.assertFalse(hasattr(self.cash_payment, 'cash_deposit'))

    def test_depositing_more_than_collected_is_fine(self):
        response = self.client.post(
            self._url(), {'amount': str(self.cash_payment.amount + 50), 'mpesa_reference': 'QWE1234569'}, format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_cannot_log_a_deposit_without_a_reference(self):
        response = self.client.post(
            self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': ''}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_reference_must_look_like_a_real_mpesa_code(self):
        for bad_reference in ('asdf', '1234567890', 'QGH7X'):
            response = self.client.post(
                self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': bad_reference}, format='json',
            )
            self.assertEqual(response.status_code, 400, f'reference={bad_reference} should have been rejected')

    def test_reference_is_normalized_to_uppercase(self):
        self.client.post(self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': 'qwe1234567'}, format='json')
        self.cash_payment.refresh_from_db()
        self.assertEqual(self.cash_payment.cash_deposit.mpesa_reference, 'QWE1234567')

    def test_cannot_log_a_second_deposit_for_the_same_payment(self):
        self.client.post(self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': 'QWE1234570'}, format='json')
        response = self.client.post(
            self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': 'QWE1234571'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_logging_a_deposit_notifies_staff_by_email(self):
        staff_user = User.objects.create_user(
            username='deposit-staff@example.com', email='deposit-staff@example.com',
            password='pass12345!', is_staff=True,
        )
        mail.outbox = []
        self.client.post(self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': 'QWE1234572'}, format='json')
        staff_emails = [m for m in mail.outbox if 'Cash deposit logged' in m.subject]
        self.assertEqual(len(staff_emails), 1)
        self.assertIn(staff_user.email, staff_emails[0].bcc)

    def test_logging_a_deposit_creates_an_admin_notification(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post(self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': 'QWE1234573'}, format='json')
        notification = Notification.objects.get(event=NotificationEvent.CASH_DEPOSIT_LOGGED)
        self.assertIn(str(self.booking.id), notification.message)

    def test_non_numeric_amount_is_rejected(self):
        response = self.client.post(self._url(), {'amount': 'abc', 'mpesa_reference': 'QWE1234572'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.cash_payment.refresh_from_db()
        self.assertFalse(hasattr(self.cash_payment, 'cash_deposit'))

    def test_cannot_log_a_deposit_for_another_drivers_payment(self):
        other_driver_user = User.objects.create_user(username='other-deposit-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Not This Driver', is_active=True)
        self.client.force_authenticate(user=other_driver_user)

        response = self.client.post(
            self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': 'QWE1234572'}, format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_log_a_deposit_for_an_mpesa_payment(self):
        mpesa_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA, amount=Decimal('100'), status=PaymentStatus.SUCCESSFUL,
        )
        response = self.client.post(
            self._url(mpesa_payment), {'amount': '100', 'mpesa_reference': 'QWE1234572'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_log_a_deposit_for_a_still_pending_cash_payment(self):
        pending_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=Decimal('100'),
            status=PaymentStatus.PENDING, recorded_by_driver=self.driver,
        )
        response = self.client.post(
            self._url(pending_payment), {'amount': '100', 'mpesa_reference': 'QWE1234572'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def _results(self, response):
        data = response.json()
        return data['results'] if 'results' in data else data

    def test_booking_lists_the_payment_as_a_pending_cash_deposit_until_logged(self):
        response = self.client.get('/api/driver/bookings/mine/')
        pending = next(b for b in self._results(response) if b['id'] == self.booking.id)['pending_cash_deposits']
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['id'], self.cash_payment.id)

        self.client.post(self._url(), {'amount': str(self.cash_payment.amount), 'mpesa_reference': 'QWE1234572'}, format='json')
        response = self.client.get('/api/driver/bookings/mine/')
        pending = next(b for b in self._results(response) if b['id'] == self.booking.id)['pending_cash_deposits']
        self.assertEqual(len(pending), 0)


class TokenPaymentPageTests(APITestCase):
    """Covers the no-login /api/pay/<token>/ page a walk-up client uses to pay."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Token Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver)
        self.customer = User.objects.create_user(username='tokenclient@example.com', password='pass12345!')
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver)

    def test_booking_summary_is_reachable_with_no_authentication(self):
        response = self.client.get(f'/api/pay/{self.booking.customer_token}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['customer_name'], self.booking.customer_name)

    def test_unknown_token_is_not_found(self):
        response = self.client.get('/api/pay/00000000-0000-0000-0000-000000000000/')
        self.assertEqual(response.status_code, 404)

    def test_stk_push_rejects_an_amount_below_the_deposit(self):
        response = self.client.post(
            f'/api/pay/{self.booking.customer_token}/stk-push/',
            {'phone_number': '254700000000', 'amount': '1'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_token_stk_push_is_throttled(self):
        # settings.py forces every throttle scope to 10000/min under 'test' so the rest of the
        # suite isn't tripped up by shared cache state - dial this one scope back down just for
        # this test to prove the throttle is actually wired up, not just configured.
        cache.clear()
        original = ScopedRateThrottle.THROTTLE_RATES.get('mpesa-stk')
        ScopedRateThrottle.THROTTLE_RATES['mpesa-stk'] = '1/min'
        try:
            self.client.post(
                f'/api/pay/{self.booking.customer_token}/stk-push/',
                {'phone_number': '254700000000', 'amount': '1'}, format='json',
            )
            response = self.client.post(
                f'/api/pay/{self.booking.customer_token}/stk-push/',
                {'phone_number': '254700000000', 'amount': '1'}, format='json',
            )
        finally:
            ScopedRateThrottle.THROTTLE_RATES['mpesa-stk'] = original
        self.assertEqual(response.status_code, 429)

    def test_stk_push_rejects_a_zero_or_negative_amount(self):
        for bad_amount in ('0', '-500'):
            response = self.client.post(
                f'/api/pay/{self.booking.customer_token}/stk-push/',
                {'phone_number': '254700000000', 'amount': bad_amount}, format='json',
            )
            self.assertEqual(response.status_code, 400, f'amount={bad_amount} should have been rejected')
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_stk_push_rejected_against_a_cancelled_booking(self):
        self.booking.status = BookingStatus.CANCELLED
        self.booking.save(update_fields=['status'])

        response = self.client.post(
            f'/api/pay/{self.booking.customer_token}/stk-push/',
            {'phone_number': '254700000000', 'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())


class DriverBookingNotificationTests(APITestCase):
    """A driver should find out the moment an online customer books them - not gated on
    payment - and be able to acknowledge it from their own dashboard."""

    def setUp(self):
        self.customer = User.objects.create_user(username='online-client@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Notify Driver', is_active=True, email='notify-driver@example.com')
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.client.force_authenticate(user=self.customer)

    def _booking_payload(self):
        return {
            'vehicle': self.vehicle.id,
            'driver': self.driver.id,
            'service_type': 'with_driver',
            'customer_name': 'Jane Doe',
            'customer_phone': '254700000000',
            'pickup_location': 'Kisumu',
            'start_date': str(TOMORROW),
            'end_date': str(NEXT_WEEK),
        }

    def test_booking_a_driver_online_notifies_them_immediately_and_unacknowledged(self):
        mail.outbox = []
        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        self.assertEqual(response.status_code, 201)

        booking = Booking.objects.get(pk=response.json()['id'])
        self.assertIsNone(booking.driver_acknowledged_at)

        driver_emails = [m for m in mail.outbox if 'New booking' in m.subject]
        self.assertEqual(len(driver_emails), 1)
        self.assertIn(self.driver.email, driver_emails[0].to)

    def test_no_driver_email_attempted_without_one_on_file(self):
        self.driver.email = ''
        self.driver.save(update_fields=['email'])
        mail.outbox = []
        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)

    @patch('bookings.emails.send_sms')
    def test_booking_a_driver_online_sms_notifies_them_immediately(self, mock_send_sms):
        self.driver.phone_number = '254711111111'
        self.driver.save(update_fields=['phone_number'])
        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        self.assertEqual(response.status_code, 201)
        mock_send_sms.assert_called_once()
        phone_arg, message_arg = mock_send_sms.call_args[0]
        self.assertEqual(phone_arg, '254711111111')
        self.assertIn(self.vehicle.name, message_arg)

    @patch('bookings.emails.send_sms')
    def test_no_driver_sms_attempted_without_a_phone_number_on_file(self, mock_send_sms):
        self.driver.phone_number = ''
        self.driver.save(update_fields=['phone_number'])
        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        self.assertEqual(response.status_code, 201)
        mock_send_sms.assert_not_called()

    @patch('bookings.emails.send_sms', side_effect=Exception('gateway down'))
    def test_a_broken_sms_gateway_never_blocks_the_booking(self, mock_send_sms):
        self.driver.phone_number = '254711111111'
        self.driver.save(update_fields=['phone_number'])
        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        self.assertEqual(response.status_code, 201)

    def test_driver_can_acknowledge_their_own_booking(self):
        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        booking_id = response.json()['id']

        driver_user = User.objects.create_user(username='driver-login@example.com', password='pass12345!')
        self.driver.user = driver_user
        self.driver.save(update_fields=['user'])

        self.client.force_authenticate(user=driver_user)
        response = self.client.post(f'/api/driver/bookings/{booking_id}/acknowledge/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()['driver_acknowledged_at'])

        booking = Booking.objects.get(pk=booking_id)
        self.assertIsNotNone(booking.driver_acknowledged_at)

    def test_booking_response_exposes_the_acknowledgment_deadline(self):
        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        data = response.json()
        self.assertIn('acknowledgment_deadline', data)
        self.assertIn('is_acknowledgment_overdue', data)
        self.assertFalse(data['is_acknowledgment_overdue'])

    def test_creating_a_booking_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post('/api/bookings/', self._booking_payload(), format='json')
        notification = Notification.objects.get(event=NotificationEvent.BOOKING_CREATED)
        self.assertIn(self.vehicle.name, notification.message)
        self.assertIn('Jane Doe', notification.message)
        self.assertEqual(notification.link_path, '/admin/bookings')

    def test_creating_a_booking_notifies_the_driver_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post('/api/bookings/', self._booking_payload(), format='json')
        notification = Notification.objects.get(event=NotificationEvent.DRIVER_BOOKED)
        self.assertEqual(notification.driver_id, self.driver.id)
        self.assertIn('Jane Doe', notification.message)
        self.assertEqual(notification.link_path, '/driver')

    def test_acknowledging_a_booking_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        booking_id = response.json()['id']

        driver_user = User.objects.create_user(username='driver-notif-login@example.com', password='pass12345!')
        self.driver.user = driver_user
        self.driver.save(update_fields=['user'])
        self.client.force_authenticate(user=driver_user)

        self.client.post(f'/api/driver/bookings/{booking_id}/acknowledge/')
        notification = Notification.objects.get(event=NotificationEvent.DRIVER_ACKNOWLEDGED)
        self.assertIn(self.driver.full_name, notification.message)
        self.assertIn(str(booking_id), notification.message)

    def test_acknowledging_an_already_acknowledged_booking_does_not_notify_twice(self):
        from notifications.models import Notification, NotificationEvent

        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        booking_id = response.json()['id']

        driver_user = User.objects.create_user(username='driver-notif-login2@example.com', password='pass12345!')
        self.driver.user = driver_user
        self.driver.save(update_fields=['user'])
        self.client.force_authenticate(user=driver_user)

        self.client.post(f'/api/driver/bookings/{booking_id}/acknowledge/')
        self.client.post(f'/api/driver/bookings/{booking_id}/acknowledge/')
        self.assertEqual(Notification.objects.filter(event=NotificationEvent.DRIVER_ACKNOWLEDGED).count(), 1)

    def test_driver_cannot_acknowledge_another_drivers_booking(self):
        response = self.client.post('/api/bookings/', self._booking_payload(), format='json')
        booking_id = response.json()['id']

        other_driver_user = User.objects.create_user(username='other-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Other Driver', is_active=True)

        self.client.force_authenticate(user=other_driver_user)
        response = self.client.post(f'/api/driver/bookings/{booking_id}/acknowledge/')
        self.assertEqual(response.status_code, 404)

    def test_driver_bookings_list_only_returns_their_own(self):
        self.client.post('/api/bookings/', self._booking_payload(), format='json')

        driver_user = User.objects.create_user(username='driver-login2@example.com', password='pass12345!')
        self.driver.user = driver_user
        self.driver.save(update_fields=['user'])

        other_driver = Driver.objects.create(full_name='Unrelated Driver', is_active=True)
        other_vehicle = make_vehicle(name='Other Car', driver=other_driver, price_per_day=Decimal('1000'))
        make_booking(self.customer, other_vehicle, driver=other_driver, status=BookingStatus.PENDING)

        self.client.force_authenticate(user=driver_user)
        response = self.client.get('/api/driver/bookings/mine/')
        self.assertEqual(response.status_code, 200)
        results = response.json()['results'] if 'results' in response.json() else response.json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['driver'], self.driver.id)

    def test_driver_sees_the_customers_rating_on_a_completed_and_reviewed_trip(self):
        driver_user = User.objects.create_user(username='rated-driver@example.com', password='pass12345!')
        self.driver.user = driver_user
        self.driver.save(update_fields=['user'])
        booking = make_booking(
            self.customer, self.vehicle, driver=self.driver, status=BookingStatus.COMPLETED,
        )
        Review.objects.create(booking=booking, driver=self.driver, customer_name='Jane Doe', rating=4, comment='Smooth ride')

        self.client.force_authenticate(user=driver_user)
        response = self.client.get('/api/driver/bookings/mine/')
        results = response.json()['results'] if 'results' in response.json() else response.json()
        self.assertEqual(results[0]['review']['rating'], 4)
        self.assertEqual(results[0]['review']['comment'], 'Smooth ride')

    def test_driver_sees_no_review_data_when_the_customer_has_not_rated_yet(self):
        driver_user = User.objects.create_user(username='unrated-driver@example.com', password='pass12345!')
        self.driver.user = driver_user
        self.driver.save(update_fields=['user'])
        make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.COMPLETED)

        self.client.force_authenticate(user=driver_user)
        response = self.client.get('/api/driver/bookings/mine/')
        results = response.json()['results'] if 'results' in response.json() else response.json()
        self.assertIsNone(results[0]['review'])

    def test_onsite_booking_is_auto_acknowledged_and_does_not_self_notify(self):
        driver_user = User.objects.create_user(username='onsite-driver@example.com', password='pass12345!')
        self.driver.user = driver_user
        self.driver.save(update_fields=['user'])

        mail.outbox = []
        self.client.force_authenticate(user=driver_user)
        response = self.client.post('/api/driver/bookings/create/', {
            'vehicle': self.vehicle.id,
            'customer_name': 'Walk Up Client',
            'customer_phone': '254700000001',
            'pickup_location': 'Kisumu Airport',
            'start_date': str(TOMORROW),
            'end_date': str(NEXT_WEEK),
        }, format='json')
        self.assertEqual(response.status_code, 201)

        booking = Booking.objects.get(pk=response.json()['booking']['id'])
        self.assertIsNotNone(booking.driver_acknowledged_at)
        self.assertEqual(len(mail.outbox), 0)


class BookingDriverDefaultingTests(APITestCase):
    """The public booking form never lets a customer pick a driver directly - without a
    server-side default, a with-driver booking would silently end up with no driver at all."""

    def setUp(self):
        self.customer = User.objects.create_user(username='defaulting-client@example.com', password='pass12345!')
        self.client.force_authenticate(user=self.customer)

    def test_with_driver_booking_defaults_to_the_vehicles_own_driver(self):
        driver = Driver.objects.create(full_name='Vehicle Owner Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))

        response = self.client.post('/api/bookings/', {
            'vehicle': vehicle.id,
            'service_type': 'with_driver',
            'customer_name': 'Jane Doe',
            'customer_phone': '254700000000',
            'pickup_location': 'Kisumu',
            'start_date': str(TOMORROW),
            'end_date': str(NEXT_WEEK),
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['driver'], driver.id)

    def test_with_driver_booking_on_a_vehicle_with_no_driver_stays_unassigned(self):
        vehicle = make_vehicle(price_per_day=Decimal('1000'))

        response = self.client.post('/api/bookings/', {
            'vehicle': vehicle.id,
            'service_type': 'with_driver',
            'customer_name': 'Jane Doe',
            'customer_phone': '254700000000',
            'pickup_location': 'Kisumu',
            'start_date': str(TOMORROW),
            'end_date': str(NEXT_WEEK),
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()['driver'])

    def test_self_drive_booking_is_not_assigned_a_driver_even_if_the_vehicle_has_one(self):
        driver = Driver.objects.create(full_name='Not Applicable Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))

        response = self.client.post('/api/bookings/', {
            'vehicle': vehicle.id,
            'service_type': 'self_drive',
            'customer_name': 'Jane Doe',
            'customer_phone': '254700000000',
            'customer_license_number': 'DL123',
            'pickup_location': 'Kisumu',
            'start_date': str(TOMORROW),
            'end_date': str(NEXT_WEEK),
            'customer_license_document': SimpleUploadedFile('license.jpg', b'x', content_type='image/jpeg'),
            'customer_id_document': SimpleUploadedFile('id.jpg', b'x', content_type='image/jpeg'),
        }, format='multipart')
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()['driver'])


class DriverBookingCompleteTests(APITestCase):
    """Lets a driver mark their own fully-paid trip complete from the portal - previously the
    only way to do this was an admin manually changing status, or a legacy no-login link
    nothing in the current UI actually points to."""

    def setUp(self):
        driver_user = User.objects.create_user(username='complete-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Complete Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='complete-client@example.com', password='pass12345!')
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED)
        self.client.force_authenticate(user=driver_user)

    def test_cannot_complete_with_an_outstanding_balance(self):
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/complete/')
        self.assertEqual(response.status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)

    def test_driver_can_complete_a_fully_paid_trip(self):
        self.booking.customer_email = 'complete-client@example.com'
        self.booking.save(update_fields=['customer_email'])
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        mail.outbox = []
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/complete/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'completed')
        self.assertTrue(any('How was your ride' in m.subject for m in mail.outbox))

    def test_cannot_complete_a_cancelled_trip(self):
        self.booking.status = BookingStatus.CANCELLED
        self.booking.save(update_fields=['status'])
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/complete/')
        self.assertEqual(response.status_code, 400)

    def test_driver_cannot_complete_another_drivers_trip(self):
        other_driver_user = User.objects.create_user(username='other-complete-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Other Driver', is_active=True)
        self.client.force_authenticate(user=other_driver_user)

        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/complete/')
        self.assertEqual(response.status_code, 404)


class DriverConditionReportTests(APITestCase):
    """A driver's optional record of the vehicle's condition at pickup/return - see
    VehicleConditionReport for why this is never required to Start/End Trip."""

    def setUp(self):
        driver_user = User.objects.create_user(username='condition-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Condition Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='condition-client@example.com', password='pass12345!')
        self.booking = make_booking(customer, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED)
        self.client.force_authenticate(user=driver_user)

    def test_driver_can_log_a_pickup_report(self):
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/condition-reports/',
            {'report_type': 'pickup', 'mileage': '45200', 'fuel_level': 'full', 'notes': 'Small scratch on rear bumper'},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['report_type'], 'pickup')
        self.assertEqual(data['mileage'], 45200)
        self.assertEqual(data['fuel_level'], 'full')
        self.assertEqual(data['logged_by_name'], 'Condition Driver')
        self.assertEqual(data['photos'], [])

    def test_photos_are_attached_to_the_report(self):
        photo1 = SimpleUploadedFile('p1.jpg', b'x', content_type='image/jpeg')
        photo2 = SimpleUploadedFile('p2.jpg', b'x', content_type='image/jpeg')
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/condition-reports/',
            {'report_type': 'pickup', 'photos': [photo1, photo2]},
            format='multipart',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()['photos']), 2)

    def test_pickup_and_return_reports_can_coexist(self):
        self.client.post(f'/api/driver/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/condition-reports/', {'report_type': 'return'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(VehicleConditionReport.objects.filter(booking=self.booking).count(), 2)

    def test_a_second_report_of_the_same_type_is_rejected(self):
        self.client.post(f'/api/driver/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(VehicleConditionReport.objects.filter(booking=self.booking, report_type='pickup').count(), 1)

    def test_invalid_report_type_is_rejected(self):
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/condition-reports/', {'report_type': 'bogus'})
        self.assertEqual(response.status_code, 400)

    def test_invalid_fuel_level_is_rejected(self):
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/condition-reports/',
            {'report_type': 'pickup', 'fuel_level': 'brimming'},
        )
        self.assertEqual(response.status_code, 400)

    def test_non_numeric_mileage_is_rejected(self):
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/condition-reports/',
            {'report_type': 'pickup', 'mileage': 'not-a-number'},
        )
        self.assertEqual(response.status_code, 400)

    def test_driver_cannot_log_a_report_for_another_drivers_booking(self):
        other_driver_user = User.objects.create_user(username='other-condition-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Other Driver', is_active=True)
        self.client.force_authenticate(user=other_driver_user)

        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        self.assertEqual(response.status_code, 404)

    def test_listing_returns_empty_when_no_reports_exist(self):
        response = self.client.get(f'/api/driver/bookings/{self.booking.id}/condition-reports/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_listing_returns_existing_reports(self):
        self.client.post(f'/api/driver/bookings/{self.booking.id}/condition-reports/', {'report_type': 'pickup'})
        response = self.client.get(f'/api/driver/bookings/{self.booking.id}/condition-reports/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]['report_type'], 'pickup')


class DriverBookingLocationTests(APITestCase):
    """A driver's own browser reports the vehicle's live position while a trip is actually in
    progress - no GPS hardware involved, so this only ever works while they have the portal
    open. Only the vehicle's latest fix is kept, not a history."""

    def setUp(self):
        driver_user = User.objects.create_user(username='location-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Location Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='location-client@example.com', password='pass12345!')
        self.booking = make_booking(
            self.customer, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            start_date=TODAY, end_date=TODAY + timedelta(days=2),
        )
        self.client.force_authenticate(user=driver_user)

    def test_driver_can_report_location_for_a_currently_active_trip(self):
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/location/', {'lat': -0.0917, 'lng': 34.7680}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.vehicle.refresh_from_db()
        self.assertEqual(float(self.vehicle.last_location_lat), -0.0917)
        self.assertEqual(float(self.vehicle.last_location_lng), 34.7680)
        self.assertIsNotNone(self.vehicle.last_location_at)

    def test_cannot_report_location_before_the_trip_starts(self):
        self.booking.start_date = TOMORROW
        self.booking.end_date = NEXT_WEEK
        self.booking.save(update_fields=['start_date', 'end_date'])
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/location/', {'lat': -0.09, 'lng': 34.76}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_report_location_for_a_pending_booking(self):
        self.booking.status = BookingStatus.PENDING
        self.booking.save(update_fields=['status'])
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/location/', {'lat': -0.09, 'lng': 34.76}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_report_location_for_a_completed_trip(self):
        self.booking.status = BookingStatus.COMPLETED
        self.booking.save(update_fields=['status'])
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/location/', {'lat': -0.09, 'lng': 34.76}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_out_of_range_coordinates(self):
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/location/', {'lat': 999, 'lng': 34.76}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_missing_coordinates(self):
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/location/', {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_driver_cannot_report_location_for_another_drivers_trip(self):
        other_driver_user = User.objects.create_user(username='other-location-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Other Driver', is_active=True)
        self.client.force_authenticate(user=other_driver_user)

        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/location/', {'lat': -0.09, 'lng': 34.76}, format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/location/', {'lat': -0.09, 'lng': 34.76}, format='json',
        )
        self.assertEqual(response.status_code, 401)


class CustomerBookingLocationTests(APITestCase):
    """The customer-facing counterpart to DriverBookingLocationTests - a customer can see their
    own vehicle's last reported position, but only within the same "trip is actually active"
    window a driver is allowed to report one in, so this never leaks a stale or premature pin."""

    def setUp(self):
        driver_user = User.objects.create_user(username='track-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Track Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='track-client@example.com', password='pass12345!')
        self.booking = make_booking(
            self.customer, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            start_date=TODAY, end_date=TODAY + timedelta(days=2),
        )
        self.client.force_authenticate(user=self.customer)

    def test_customer_sees_the_vehicles_last_reported_position(self):
        self.vehicle.last_location_lat = -0.0917
        self.vehicle.last_location_lng = 34.7680
        self.vehicle.last_location_at = timezone.now()
        self.vehicle.save(update_fields=['last_location_lat', 'last_location_lng', 'last_location_at'])

        response = self.client.get(f'/api/bookings/{self.booking.id}/location/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['tracking_available'])
        self.assertEqual(float(response.data['last_location_lat']), -0.0917)
        self.assertEqual(response.data['driver_name'], 'Track Driver')

    def test_tracking_unavailable_before_the_driver_has_reported_a_position(self):
        response = self.client.get(f'/api/bookings/{self.booking.id}/location/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['tracking_available'])

    def test_tracking_unavailable_for_a_pending_booking(self):
        self.vehicle.last_location_lat = -0.09
        self.vehicle.last_location_lng = 34.76
        self.vehicle.save(update_fields=['last_location_lat', 'last_location_lng'])
        self.booking.status = BookingStatus.PENDING
        self.booking.save(update_fields=['status'])

        response = self.client.get(f'/api/bookings/{self.booking.id}/location/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['tracking_available'])

    def test_tracking_unavailable_before_the_trip_dates_start(self):
        self.vehicle.last_location_lat = -0.09
        self.vehicle.last_location_lng = 34.76
        self.vehicle.save(update_fields=['last_location_lat', 'last_location_lng'])
        self.booking.start_date = TOMORROW
        self.booking.end_date = NEXT_WEEK
        self.booking.save(update_fields=['start_date', 'end_date'])

        response = self.client.get(f'/api/bookings/{self.booking.id}/location/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['tracking_available'])

    def test_tracking_unavailable_for_a_completed_trip(self):
        self.vehicle.last_location_lat = -0.09
        self.vehicle.last_location_lng = 34.76
        self.vehicle.save(update_fields=['last_location_lat', 'last_location_lng'])
        self.booking.status = BookingStatus.COMPLETED
        self.booking.save(update_fields=['status'])

        response = self.client.get(f'/api/bookings/{self.booking.id}/location/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['tracking_available'])

    def test_customer_cannot_see_location_for_someone_elses_booking(self):
        other_customer = User.objects.create_user(username='other-track-client@example.com', password='pass12345!')
        self.client.force_authenticate(user=other_customer)

        response = self.client.get(f'/api/bookings/{self.booking.id}/location/')
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(f'/api/bookings/{self.booking.id}/location/')
        self.assertEqual(response.status_code, 401)


class BookingReceiptTests(APITestCase):
    """A downloadable PDF receipt - only ever offered once at least one payment has actually
    succeeded. Scoped through the same get_object()/get_queryset() as the rest of
    BookingViewSet, so a customer only ever gets their own."""

    def setUp(self):
        self.customer = User.objects.create_user(username='receipt-client@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.booking = make_booking(self.customer, self.vehicle, status=BookingStatus.CONFIRMED)
        self.client.force_authenticate(user=self.customer)

    def test_receipt_requires_at_least_one_successful_payment(self):
        response = self.client.get(f'/api/bookings/{self.booking.id}/receipt/')
        self.assertEqual(response.status_code, 400)

    def test_receipt_downloads_as_a_pdf_once_paid(self):
        Payment.objects.create(booking=self.booking, amount=self.booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)
        response = self.client.get(f'/api/bookings/{self.booking.id}/receipt/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(f'SilverLake-Receipt-{self.booking.id}.pdf', response['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'%PDF'))

    def test_a_pending_unpaid_payment_does_not_unlock_the_receipt(self):
        Payment.objects.create(booking=self.booking, amount=self.booking.deposit_amount, status=PaymentStatus.PENDING)
        response = self.client.get(f'/api/bookings/{self.booking.id}/receipt/')
        self.assertEqual(response.status_code, 400)

    def test_customer_cannot_download_someone_elses_receipt(self):
        Payment.objects.create(booking=self.booking, amount=self.booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)
        other_customer = User.objects.create_user(username='other-receipt-client@example.com', password='pass12345!')
        self.client.force_authenticate(user=other_customer)
        response = self.client.get(f'/api/bookings/{self.booking.id}/receipt/')
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_request_is_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(f'/api/bookings/{self.booking.id}/receipt/')
        self.assertEqual(response.status_code, 401)

    def test_staff_can_download_a_receipt_for_any_booking(self):
        Payment.objects.create(booking=self.booking, amount=self.booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)
        staff = User.objects.create_user(username='receipt-staff@example.com', password='pass12345!', is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(f'/api/bookings/{self.booking.id}/receipt/')
        self.assertEqual(response.status_code, 200)


class TripLifecycleTests(APITestCase):
    """Separates three distinct facts that used to be conflated: money arriving, the driver
    confirming the car was handed over, and the driver confirming it came back. Paying in full
    doesn't by itself mean a trip happened - the balance is due 'on or before pickup', so it can
    clear before the trip even starts."""

    def setUp(self):
        self.driver_user = User.objects.create_user(username='trip-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=self.driver_user, full_name='Trip Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='trip-client@example.com', password='pass12345!')
        self.booking = make_booking(
            self.customer, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            customer_email='trip-client@example.com',
        )
        self.client.force_authenticate(user=self.driver_user)

    def test_start_trip_moves_to_ongoing_and_stamps_a_timestamp(self):
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/start-trip/')
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.ONGOING)
        self.assertIsNotNone(self.booking.trip_started_at)

    def test_cannot_start_a_trip_that_is_still_pending(self):
        self.booking.status = BookingStatus.PENDING
        self.booking.save(update_fields=['status'])
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/start-trip/')
        self.assertEqual(response.status_code, 400)

    def test_cannot_start_a_trip_twice(self):
        self.client.post(f'/api/driver/bookings/{self.booking.id}/start-trip/')
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/start-trip/')
        self.assertEqual(response.status_code, 400)

    def test_ending_an_unpaid_trip_stays_open_but_records_the_end_time(self):
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/end-trip/')
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.booking.trip_ended_at)
        self.assertNotEqual(self.booking.status, BookingStatus.COMPLETED)

    def test_ending_a_fully_paid_trip_completes_it_immediately(self):
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        mail.outbox = []
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/end-trip/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'completed')
        self.assertTrue(any('How was your ride' in m.subject for m in mail.outbox))

    def test_completing_a_trip_notifies_the_client_in_app(self):
        from notifications.models import Notification, NotificationEvent

        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.client.post(f'/api/driver/bookings/{self.booking.id}/end-trip/')
        notification = Notification.objects.get(event=NotificationEvent.TRIP_COMPLETED)
        self.assertEqual(notification.user_id, self.customer.id)
        self.assertIn(str(self.booking.id), notification.message)

    def test_a_late_payment_after_the_trip_already_ended_completes_it(self):
        # The driver confirms the car is back first, while a balance is still owed.
        self.client.post(f'/api/driver/bookings/{self.booking.id}/end-trip/')
        self.booking.refresh_from_db()
        self.assertNotEqual(self.booking.status, BookingStatus.COMPLETED)

        # The remaining balance clears afterwards - this is the one case where payment alone is
        # allowed to complete the booking, because the trip was already confirmed physically over.
        mail.outbox = []
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.booking.confirm_if_deposit_met()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.COMPLETED)
        self.assertTrue(any('How was your ride' in m.subject for m in mail.outbox))

    def test_paying_in_full_before_the_trip_ends_does_not_auto_complete_it(self):
        # This is the exact scenario that made payment-triggered completion unsafe on its own -
        # the balance can clear well before the car has even left.
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.booking.confirm_if_deposit_met()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)
        self.assertIsNone(self.booking.trip_ended_at)

    def test_cannot_end_a_cancelled_trip(self):
        self.booking.status = BookingStatus.CANCELLED
        self.booking.save(update_fields=['status'])
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/end-trip/')
        self.assertEqual(response.status_code, 400)

    def test_driver_cannot_start_or_end_another_drivers_trip(self):
        other_driver_user = User.objects.create_user(username='other-trip-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Other Driver', is_active=True)
        self.client.force_authenticate(user=other_driver_user)

        start_response = self.client.post(f'/api/driver/bookings/{self.booking.id}/start-trip/')
        end_response = self.client.post(f'/api/driver/bookings/{self.booking.id}/end-trip/')
        self.assertEqual(start_response.status_code, 404)
        self.assertEqual(end_response.status_code, 404)

    def test_direct_complete_also_stamps_trip_ended_at(self):
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.client.post(f'/api/driver/bookings/{self.booking.id}/complete/')
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.booking.trip_ended_at)

    def test_undeposited_cash_holds_back_completion_even_though_the_balance_is_zero(self):
        # The client genuinely paid in cash - balance_due already reflects that - but the trip
        # can't complete until the driver hands that cash over to SilverLake too.
        self.client.post(f'/api/driver/bookings/{self.booking.id}/end-trip/')
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.booking.confirm_if_deposit_met()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.balance_due, Decimal('0.00'))
        self.assertNotEqual(self.booking.status, BookingStatus.COMPLETED)

    def test_logging_the_cash_deposit_completes_a_trip_that_was_only_waiting_on_it(self):
        self.client.post(f'/api/driver/bookings/{self.booking.id}/end-trip/')
        payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.booking.confirm_if_deposit_met()
        self.booking.refresh_from_db()
        self.assertNotEqual(self.booking.status, BookingStatus.COMPLETED)

        mail.outbox = []
        response = self.client.post(
            f'/api/driver/payments/{payment.id}/deposit/',
            {'amount': str(self.booking.total_amount), 'mpesa_reference': 'QGH7ABCDEF'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'completed')
        self.assertTrue(any('How was your ride' in m.subject for m in mail.outbox))

    def test_cannot_manually_complete_a_trip_with_undeposited_cash(self):
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        response = self.client.post(f'/api/driver/bookings/{self.booking.id}/complete/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('deposit', response.json()['detail'].lower())
        self.booking.refresh_from_db()
        self.assertNotEqual(self.booking.status, BookingStatus.COMPLETED)


class NeedsAttentionTests(APITestCase):
    """A booking whose scheduled window has passed but is still open (nobody ever confirmed it
    started/ended, or it ended but is still unpaid) is surfaced to admins as a nudge - nothing
    ever resolves it automatically."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(username='attention-super@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='attention-client@example.com', password='pass12345!')

    def test_a_confirmed_booking_past_its_end_date_needs_attention(self):
        booking = make_booking(
            self.customer, self.vehicle, status=BookingStatus.CONFIRMED,
            start_date=TODAY - timedelta(days=5), end_date=TODAY - timedelta(days=1),
        )
        self.assertTrue(booking.needs_attention)

    def test_a_booking_still_within_its_dates_does_not_need_attention(self):
        booking = make_booking(self.customer, self.vehicle, status=BookingStatus.CONFIRMED)
        self.assertFalse(booking.needs_attention)

    def test_a_completed_booking_never_needs_attention_regardless_of_dates(self):
        booking = make_booking(
            self.customer, self.vehicle, status=BookingStatus.COMPLETED,
            start_date=TODAY - timedelta(days=5), end_date=TODAY - timedelta(days=1),
        )
        self.assertFalse(booking.needs_attention)

    def test_admin_stats_counts_bookings_needing_attention(self):
        make_booking(
            self.customer, self.vehicle, status=BookingStatus.CONFIRMED,
            start_date=TODAY - timedelta(days=5), end_date=TODAY - timedelta(days=1),
        )
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get('/api/admin/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['bookings']['needing_attention'], 1)


class BookingRaceConditionTests(TransactionTestCase):
    """Proves two concurrent requests for the same vehicle/dates can't both succeed. Needs
    TransactionTestCase (not the usual TestCase) and real threads with their own DB connections
    to reproduce a genuine race - a single-connection test can't. See BookingViewSet.create()
    for why plain select_for_update() doesn't actually work here (SQLite doesn't support it -
    Django silently drops the clause rather than locking anything)."""

    def setUp(self):
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.user_a = User.objects.create_user(username='race-a@example.com', password='pass12345!')
        self.user_b = User.objects.create_user(username='race-b@example.com', password='pass12345!')

    def _payload(self):
        return {
            'vehicle': self.vehicle.id, 'service_type': 'with_driver',
            'customer_name': 'Racer', 'customer_phone': '254700000000',
            'pickup_location': 'Kisumu', 'start_date': str(TOMORROW), 'end_date': str(NEXT_WEEK),
        }

    def test_two_concurrent_bookings_for_the_same_vehicle_and_dates_dont_both_succeed(self):
        # Widen the window between the conflict-check read and the write that follows it, so
        # the second thread's own conflict check has time to run while the first is still
        # mid-transaction - this is what actually creates the race in the first place (both
        # threads see "no conflict" before either has written anything).
        original_clean = Booking.clean

        def slow_clean(booking, *args, **kwargs):
            result = original_clean(booking, *args, **kwargs)
            time.sleep(0.3)
            return result

        results = {}

        def attempt(user, key):
            client = APIClient()
            client.force_authenticate(user=user)
            response = client.post('/api/bookings/', self._payload(), format='json')
            results[key] = response.status_code
            connection.close()

        with patch.object(Booking, 'clean', slow_clean):
            t1 = threading.Thread(target=attempt, args=(self.user_a, 'a'))
            t2 = threading.Thread(target=attempt, args=(self.user_b, 'b'))
            t1.start()
            time.sleep(0.05)  # give thread 1 a head start into its transaction
            t2.start()
            t1.join()
            t2.join()

        # Whichever thread loses gets either a clean 400 (its own conflict check saw the
        # winner's already-committed booking) or a 409 (it hit the vehicle lock directly and
        # gave up rather than waiting forever) - either way, exactly one booking gets created.
        statuses = sorted(results.values())
        self.assertEqual(len(statuses), 2, f'expected both requests to get a response, got {results}')
        self.assertEqual(statuses.count(201), 1, f'expected exactly one booking to succeed, got {results}')
        self.assertIn(statuses[0] if statuses[1] == 201 else statuses[1], (400, 409))
        self.assertEqual(Booking.objects.filter(vehicle=self.vehicle).count(), 1)


class BookingDocumentReplacementCleanupTests(APITestCase):
    """A customer can PATCH their own booking to re-upload a corrected license/ID document -
    reassigning a FileField and saving doesn't make Django delete the file that used to be
    there, so without explicit cleanup the old document would be orphaned in storage forever
    every time someone fixes a bad upload."""

    def _png(self, name):
        import base64
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        return SimpleUploadedFile(name, png, content_type='image/png')

    def setUp(self):
        self.user = User.objects.create_user(username='doc-cleanup@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.booking = make_booking(self.user, self.vehicle, service_type=ServiceType.SELF_DRIVE)
        self.booking.customer_license_document.save('first.png', self._png('first.png'), save=False)
        self.booking.customer_id_document.save('id.png', self._png('id.png'), save=True)
        self.client.force_authenticate(user=self.user)

    def test_replacing_a_license_document_deletes_the_old_file(self):
        old_name = self.booking.customer_license_document.name
        self.assertTrue(self.booking.customer_license_document.storage.exists(old_name))

        response = self.client.patch(
            f'/api/bookings/{self.booking.id}/',
            {'customer_license_document': self._png('second.png')}, format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        self.booking.refresh_from_db()
        self.assertNotEqual(self.booking.customer_license_document.name, old_name)
        self.assertFalse(self.booking.customer_license_document.storage.exists(old_name))


class DriverAcknowledgmentDeadlineTests(TestCase):
    """A same-day pickup gets a tighter acknowledgment deadline than one booked further ahead -
    see Booking.acknowledgment_deadline."""

    def setUp(self):
        self.user = User.objects.create_user(username='ack-deadline-client@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.driver = Driver.objects.create(full_name='Ack Deadline Driver', is_active=True)

    def test_same_day_booking_gets_a_one_hour_deadline(self):
        booking = make_booking(
            self.user, self.vehicle, driver=self.driver, start_date=TODAY, end_date=TOMORROW,
        )
        self.assertEqual(booking.acknowledgment_deadline, booking.created_at + timedelta(hours=1))

    def test_future_booking_gets_a_two_hour_deadline(self):
        booking = make_booking(
            self.user, self.vehicle, driver=self.driver, start_date=NEXT_WEEK, end_date=NEXT_WEEK + timedelta(days=1),
        )
        self.assertEqual(booking.acknowledgment_deadline, booking.created_at + timedelta(hours=2))

    def test_is_acknowledgment_overdue_false_before_deadline(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver, start_date=TODAY, end_date=TOMORROW)
        self.assertFalse(booking.is_acknowledgment_overdue)

    def test_is_acknowledgment_overdue_true_after_deadline(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver, start_date=TODAY, end_date=TOMORROW)
        Booking.objects.filter(pk=booking.pk).update(created_at=timezone.now() - timedelta(hours=2))
        booking.refresh_from_db()
        self.assertTrue(booking.is_acknowledgment_overdue)

    def test_not_overdue_once_acknowledged(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver, start_date=TODAY, end_date=TOMORROW)
        Booking.objects.filter(pk=booking.pk).update(
            created_at=timezone.now() - timedelta(hours=2), driver_acknowledged_at=timezone.now(),
        )
        booking.refresh_from_db()
        self.assertFalse(booking.is_acknowledgment_overdue)

    def test_not_overdue_once_trip_started(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver, start_date=TODAY, end_date=TOMORROW)
        Booking.objects.filter(pk=booking.pk).update(
            created_at=timezone.now() - timedelta(hours=2), trip_started_at=timezone.now(),
        )
        booking.refresh_from_db()
        self.assertFalse(booking.is_acknowledgment_overdue)

    def test_walk_in_bookings_are_never_overdue(self):
        # Auto-acknowledged at creation (see DriverOnsiteBookingCreateView) - driver_acknowledged_at
        # is never null for these, so is_acknowledgment_overdue is trivially always false.
        booking = make_booking(
            self.user, self.vehicle, driver=self.driver, start_date=TODAY, end_date=TOMORROW,
            source=BookingSource.DRIVER_ONSITE, driver_acknowledged_at=timezone.now(),
        )
        Booking.objects.filter(pk=booking.pk).update(created_at=timezone.now() - timedelta(hours=2))
        booking.refresh_from_db()
        self.assertFalse(booking.is_acknowledgment_overdue)


class CustomerTokenExpiryTests(TestCase):
    """The no-login customer_token link (payment page + cash-payment dispute page) stays live
    through the trip plus a grace period afterward, not permanently - see
    Booking.customer_token_expires_at."""

    def setUp(self):
        self.user = User.objects.create_user(username='token-expiry-client@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))

    def test_expires_at_is_grace_period_after_end_date(self):
        booking = make_booking(self.user, self.vehicle, start_date=TOMORROW, end_date=NEXT_WEEK)
        self.assertEqual(booking.customer_token_expires_at, NEXT_WEEK + timedelta(days=14))

    def test_not_expired_within_the_grace_period(self):
        booking = make_booking(self.user, self.vehicle, start_date=TOMORROW, end_date=TOMORROW)
        self.assertFalse(booking.is_customer_token_expired)

    def test_expired_once_grace_period_has_passed(self):
        long_ago_start = TODAY - timedelta(days=60)
        long_ago_end = TODAY - timedelta(days=59)
        booking = make_booking(self.user, self.vehicle, start_date=long_ago_start, end_date=long_ago_end)
        self.assertTrue(booking.is_customer_token_expired)


class EscalateUnacknowledgedBookingsTests(APITestCase):
    """The automated counterpart to a staff member noticing an online booking's driver hasn't
    acknowledged it - alerts staff once, past the deadline, with no automatic reassignment."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Escalation Ack Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='ack-escalation-client@example.com', password='pass12345!')

    def _run(self):
        from bookings.services import escalate_unacknowledged_bookings

        escalate_unacknowledged_bookings()

    def _make_overdue_booking(self, **kwargs):
        kwargs.setdefault('status', BookingStatus.PENDING)
        booking = make_booking(
            self.customer, self.vehicle, driver=self.driver,
            start_date=TODAY, end_date=TOMORROW, **kwargs,
        )
        Booking.objects.filter(pk=booking.pk).update(created_at=timezone.now() - timedelta(hours=2))
        booking.refresh_from_db()
        return booking

    def test_overdue_booking_gets_a_staff_email(self):
        staff = User.objects.create_user(
            username='ack-escalation-staff@example.com', email='ack-escalation-staff@example.com',
            password='pass12345!', is_staff=True,
        )
        booking = self._make_overdue_booking()
        mail.outbox = []
        self._run()
        booking.refresh_from_db()
        self.assertIsNotNone(booking.ack_escalated_at)
        staff_emails = [m for m in mail.outbox if "hasn't acknowledged" in m.subject]
        self.assertEqual(len(staff_emails), 1)
        self.assertIn(staff.email, staff_emails[0].bcc)

    def test_overdue_booking_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        booking = self._make_overdue_booking()
        self._run()
        notification = Notification.objects.get(event=NotificationEvent.ACKNOWLEDGMENT_OVERDUE)
        self.assertIn(str(booking.id), notification.message)

    def test_escalation_links_directly_to_the_booking_in_the_admin_list(self):
        from notifications.models import Notification, NotificationEvent

        booking = self._make_overdue_booking()
        self._run()
        notification = Notification.objects.get(event=NotificationEvent.ACKNOWLEDGMENT_OVERDUE)
        self.assertIn(f'/admin/bookings?search=', notification.link_path)
        self.assertIn(booking.customer_name.replace(' ', '%20'), notification.link_path)

    def test_not_yet_overdue_booking_is_left_alone(self):
        booking = make_booking(
            self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING,
            start_date=TODAY, end_date=TOMORROW,
        )
        mail.outbox = []
        self._run()
        booking.refresh_from_db()
        self.assertIsNone(booking.ack_escalated_at)

    def test_already_acknowledged_booking_is_left_alone(self):
        booking = self._make_overdue_booking(driver_acknowledged_at=timezone.now())
        mail.outbox = []
        self._run()
        booking.refresh_from_db()
        self.assertIsNone(booking.ack_escalated_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_escalation_only_ever_fires_once(self):
        booking = self._make_overdue_booking()
        self._run()
        mail.outbox = []
        self._run()
        self.assertEqual(len(mail.outbox), 0)

    def test_cancelled_booking_is_left_alone(self):
        booking = self._make_overdue_booking(status=BookingStatus.CANCELLED)
        mail.outbox = []
        self._run()
        booking.refresh_from_db()
        self.assertIsNone(booking.ack_escalated_at)


class ExpireStalePendingBookingsTests(APITestCase):
    """An abandoned checkout - a PENDING booking nobody ever paid anything toward - shouldn't
    block a vehicle from public visibility or from being booked by someone else forever. See
    bookings.services.expire_stale_pending_bookings / STALE_PENDING_BOOKING_THRESHOLD."""

    def setUp(self):
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='stale-pending-client@example.com', password='pass12345!')

    def _run(self):
        from bookings.services import expire_stale_pending_bookings

        return expire_stale_pending_bookings()

    def _make_stale_booking(self, **kwargs):
        kwargs.setdefault('status', BookingStatus.PENDING)
        booking = make_booking(self.customer, self.vehicle, start_date=TODAY, end_date=TOMORROW, **kwargs)
        Booking.objects.filter(pk=booking.pk).update(created_at=timezone.now() - timedelta(hours=25))
        booking.refresh_from_db()
        return booking

    def test_unpaid_pending_booking_older_than_the_threshold_is_cancelled(self):
        booking = self._make_stale_booking()
        count = self._run()
        booking.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(booking.status, BookingStatus.CANCELLED)

    def test_customer_is_notified_by_email(self):
        booking = self._make_stale_booking(customer_email='stale-pending-client@example.com')
        mail.outbox = []
        self._run()
        self.assertTrue(len(mail.outbox) >= 1)

    def test_a_booking_younger_than_the_threshold_is_left_alone(self):
        booking = make_booking(
            self.customer, self.vehicle, status=BookingStatus.PENDING, start_date=TODAY, end_date=TOMORROW,
        )
        count = self._run()
        booking.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(booking.status, BookingStatus.PENDING)

    def test_a_booking_with_a_successful_payment_is_left_alone(self):
        booking = self._make_stale_booking()
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)
        count = self._run()
        booking.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(booking.status, BookingStatus.PENDING)

    def test_a_booking_with_a_pending_cash_declaration_is_left_alone(self):
        # Represents real in-progress intent (e.g. a driver-declared cash handoff awaiting
        # confirmation) - shouldn't be nuked by an automatic sweep just because it's old.
        booking = self._make_stale_booking()
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.PENDING)
        count = self._run()
        booking.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(booking.status, BookingStatus.PENDING)

    def test_a_booking_with_only_a_failed_payment_is_still_expired(self):
        # A failed/abandoned M-Pesa attempt (already marked FAILED by expire_stale_mpesa_payments)
        # is not "activity in progress" - this booking is just as abandoned as one with no
        # payment record at all.
        booking = self._make_stale_booking()
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.FAILED)
        count = self._run()
        booking.refresh_from_db()
        self.assertEqual(count, 1)
        self.assertEqual(booking.status, BookingStatus.CANCELLED)

    def test_a_confirmed_booking_is_left_alone_regardless_of_age(self):
        booking = self._make_stale_booking(status=BookingStatus.CONFIRMED)
        count = self._run()
        booking.refresh_from_db()
        self.assertEqual(count, 0)
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)

class SelfDriveSurchargeTests(TestCase):
    """Self-drive costs 3% more than the vehicle's own with-driver rate - the customer is
    driving SilverLake's own vehicle themselves, which carries more risk/liability than a
    booking with a driver at the wheel."""

    def setUp(self):
        self.user = User.objects.create_user(username='surcharge-client@example.com', password='pass12345!')
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))

    def test_with_driver_booking_has_no_surcharge(self):
        booking = make_booking(
            self.user, self.vehicle, service_type=ServiceType.WITH_DRIVER,
            start_date=TOMORROW, end_date=TOMORROW,
        )
        self.assertEqual(booking.total_amount, Decimal('1000.00'))

    def test_self_drive_booking_gets_a_three_percent_surcharge(self):
        booking = make_booking(
            self.user, self.vehicle, service_type=ServiceType.SELF_DRIVE,
            start_date=TOMORROW, end_date=TOMORROW,
        )
        self.assertEqual(booking.total_amount, Decimal('1030.00'))

    def test_surcharge_is_rounded_to_two_decimal_places(self):
        vehicle = make_vehicle(name='Odd Rate Car', price_per_day=Decimal('999.99'))
        booking = make_booking(
            self.user, vehicle, service_type=ServiceType.SELF_DRIVE,
            start_date=TOMORROW, end_date=TOMORROW,
        )
        # 999.99 * 1.03 = 1029.9897 -> rounds to 1029.99
        self.assertEqual(booking.total_amount, Decimal('1029.99'))

    def test_surcharge_applies_across_multiple_days(self):
        booking = make_booking(
            self.user, self.vehicle, service_type=ServiceType.SELF_DRIVE,
            start_date=TOMORROW, end_date=TOMORROW + timedelta(days=3),
        )
        # 4 days (inclusive) * 1000 = 4000, + 3% = 4120.00
        self.assertEqual(booking.rental_days, 4)
        self.assertEqual(booking.total_amount, Decimal('4120.00'))
