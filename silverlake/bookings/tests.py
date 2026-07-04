from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APITestCase

from drivers.models import Driver
from fleet.models import Vehicle
from payments.models import Payment, PaymentStatus
from reviews.models import Review

from .models import Booking, BookingStatus, ServiceType

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
