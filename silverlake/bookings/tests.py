from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APITestCase

from drivers.models import Driver
from fleet.models import Vehicle
from payments.models import DriverPayout, Payment, PaymentMethod, PaymentStatus
from reviews.models import Review

from .models import Booking, BookingSource, BookingStatus, ServiceType

User = get_user_model()

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)
NEXT_WEEK = TODAY + timedelta(days=7)


def make_vehicle(**kwargs):
    defaults = dict(
        name='Test Car', category='compact_sedan', passenger_capacity=4,
        price_per_day=Decimal('1000'), is_available=True,
    )
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
        self.vehicle = make_vehicle(price_per_day=Decimal('1000'))
        self.driver = Driver.objects.create(full_name='Driver One', is_active=True)

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

    def test_confirm_if_deposit_met_only_confirms_once_and_creates_payout(self):
        booking = make_booking(self.user, self.vehicle, driver=self.driver)
        Payment.objects.create(booking=booking, amount=booking.deposit_amount, status=PaymentStatus.SUCCESSFUL)

        booking.confirm_if_deposit_met()
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CONFIRMED)
        self.assertEqual(booking.driver_payout.amount, booking.driver_payout_amount)

        # Calling again should be a no-op, not raise or duplicate the payout.
        booking.confirm_if_deposit_met()
        self.assertEqual(booking.driver.payouts.filter(booking=booking).count(), 1)


class BookingCancelActionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='jane@example.com', password='pass12345!')
        self.vehicle = make_vehicle()
        self.client.force_authenticate(user=self.user)

    def test_can_cancel_a_pending_booking(self):
        booking = make_booking(self.user, self.vehicle, status=BookingStatus.PENDING)
        response = self.client.post(f'/api/bookings/{booking.id}/cancel/')
        self.assertEqual(response.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)

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


class DriverCashPaymentTests(APITestCase):
    def setUp(self):
        driver_user = User.objects.create_user(username='cash-driver@example.com', password='pass12345!')
        self.driver = Driver.objects.create(user=driver_user, full_name='Cash Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='client@example.com', password='pass12345!')
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING)
        self.client.force_authenticate(user=driver_user)

    def test_driver_can_record_cash_for_their_own_booking(self):
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/record-cash/',
            {'amount': str(self.booking.deposit_amount), 'note': 'Paid at pickup'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)

        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.method, PaymentMethod.CASH)
        self.assertEqual(payment.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(payment.recorded_by_driver_id, self.driver.id)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)  # deposit met -> auto-confirmed

    def test_cannot_record_cash_for_another_drivers_booking(self):
        other_driver_user = User.objects.create_user(username='other-driver@example.com', password='pass12345!')
        Driver.objects.create(user=other_driver_user, full_name='Not This Driver', is_active=True)
        self.client.force_authenticate(user=other_driver_user)

        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/record-cash/', {'amount': '100'}, format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_record_cash_exceeding_the_balance_due(self):
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/record-cash/',
            {'amount': str(self.booking.total_amount + 1)}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_cash_payment_flags_its_payout_as_needing_verification(self):
        self.client.post(
            f'/api/driver/bookings/{self.booking.id}/record-cash/',
            {'amount': str(self.booking.deposit_amount)}, format='json',
        )
        payout = DriverPayout.objects.get(booking=self.booking)
        self.assertTrue(payout.needs_verification)
        self.assertFalse(payout.is_verified)

    def test_mpesa_confirmed_payout_does_not_need_verification(self):
        # Simulate a successful M-Pesa payment (as the callback would record it) instead of cash.
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.deposit_amount, status=PaymentStatus.SUCCESSFUL,
        )
        self.booking.confirm_if_deposit_met()
        payout = DriverPayout.objects.get(booking=self.booking)
        self.assertFalse(payout.needs_verification)

    def test_cash_payment_emails_the_customer_as_an_independent_check(self):
        self.booking.customer_email = 'client@example.com'
        self.booking.save(update_fields=['customer_email'])

        mail.outbox = []
        self.client.post(
            f'/api/driver/bookings/{self.booking.id}/record-cash/',
            {'amount': str(self.booking.deposit_amount)}, format='json',
        )
        # The deposit-confirmation email also fires alongside this one - both legitimately
        # go to the customer, so just confirm the cash-payment notice is among them.
        cash_emails = [m for m in mail.outbox if 'Cash payment recorded' in m.subject]
        self.assertEqual(len(cash_emails), 1)
        self.assertIn(self.booking.customer_email, cash_emails[0].to)

    def test_no_email_attempted_without_a_customer_email_on_file(self):
        self.assertEqual(self.booking.customer_email, '')
        mail.outbox = []
        response = self.client.post(
            f'/api/driver/bookings/{self.booking.id}/record-cash/',
            {'amount': str(self.booking.deposit_amount)}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


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
