from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from bookings.models import BookingStatus
from bookings.tests import make_booking, make_vehicle
from drivers.models import Driver

from .models import Payment, PaymentMethod, PaymentStatus
from .services import PaymentValidationError, initiate_stk_push_payment

User = get_user_model()

REAL_SECRET = 'test-callback-secret'


def callback_body(checkout_request_id, result_code=0, receipt='NLJ7RT61SV'):
    body = {
        'Body': {
            'stkCallback': {
                'CheckoutRequestID': checkout_request_id,
                'ResultCode': result_code,
            }
        }
    }
    if result_code == 0:
        body['Body']['stkCallback']['CallbackMetadata'] = {
            'Item': [{'Name': 'MpesaReceiptNumber', 'Value': receipt}]
        }
    return body


class MpesaCallbackSecurityTests(APITestCase):
    """A forged callback shouldn't be able to mark a payment successful - the CheckoutRequestID
    it's keyed on is visible to the customer's own browser, so the secret path segment is what
    actually stops anyone from faking Safaricom's confirmation."""

    def setUp(self):
        driver = Driver.objects.create(full_name='Callback Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='callback-client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=driver, status=BookingStatus.PENDING)
        self.payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.deposit_amount, status=PaymentStatus.PENDING,
            mpesa_checkout_request_id='ws_CO_real_checkout_id',
        )

    @patch('payments.views.config')
    def test_wrong_secret_is_rejected_and_payment_is_untouched(self, mock_config):
        mock_config.side_effect = lambda key, default='': REAL_SECRET if key == 'MPESA_CALLBACK_SECRET' else default
        response = self.client.post(
            '/api/payments/mpesa/callback/not-the-real-secret/',
            callback_body('ws_CO_real_checkout_id'), format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)

    @patch('payments.views.config')
    def test_missing_secret_configuration_rejects_everything(self, mock_config):
        # No MPESA_CALLBACK_SECRET set at all - refuse every callback rather than silently
        # accepting an unguarded one.
        mock_config.side_effect = lambda key, default='': default
        response = self.client.post(
            '/api/payments/mpesa/callback/anything/',
            callback_body('ws_CO_real_checkout_id'), format='json',
        )
        self.assertEqual(response.status_code, 404)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)

    @patch('payments.views.config')
    def test_correct_secret_with_successful_result_confirms_payment_and_booking(self, mock_config):
        mock_config.side_effect = lambda key, default='': REAL_SECRET if key == 'MPESA_CALLBACK_SECRET' else default
        response = self.client.post(
            f'/api/payments/mpesa/callback/{REAL_SECRET}/',
            callback_body('ws_CO_real_checkout_id', result_code=0), format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(self.payment.mpesa_receipt_number, 'NLJ7RT61SV')

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)

    @patch('payments.views.config')
    def test_correct_secret_with_failed_result_marks_payment_failed(self, mock_config):
        mock_config.side_effect = lambda key, default='': REAL_SECRET if key == 'MPESA_CALLBACK_SECRET' else default
        response = self.client.post(
            f'/api/payments/mpesa/callback/{REAL_SECRET}/',
            callback_body('ws_CO_real_checkout_id', result_code=1), format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.FAILED)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.PENDING)


class PaymentStatusPollingTests(APITestCase):
    """Lets the frontend poll whether an STK push actually went through, instead of leaving the
    customer staring at "check your phone" forever with no way to know if it failed."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Polling Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='polling-client@example.com', password='pass12345!')
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING)
        self.payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.deposit_amount, status=PaymentStatus.PENDING,
        )

    def test_owner_can_poll_their_own_payment_status(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(f'/api/payments/{self.payment.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'pending')

    def test_another_customer_cannot_poll_someone_elses_payment(self):
        other_customer = User.objects.create_user(username='other-polling@example.com', password='pass12345!')
        self.client.force_authenticate(user=other_customer)
        response = self.client.get(f'/api/payments/{self.payment.id}/')
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_cannot_poll_a_payment(self):
        response = self.client.get(f'/api/payments/{self.payment.id}/')
        self.assertEqual(response.status_code, 401)

    def test_staff_can_poll_any_payment(self):
        staff = User.objects.create_user(username='polling-staff@example.com', password='pass12345!', is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(f'/api/payments/{self.payment.id}/')
        self.assertEqual(response.status_code, 200)

    def test_token_payment_status_reflects_the_real_payment(self):
        self.payment.status = PaymentStatus.SUCCESSFUL
        self.payment.save(update_fields=['status'])
        response = self.client.get(f'/api/pay/{self.booking.customer_token}/payments/{self.payment.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'successful')

    def test_token_payment_status_rejects_a_payment_from_a_different_booking(self):
        other_customer = User.objects.create_user(username='other-token-client@example.com', password='pass12345!')
        other_booking = make_booking(other_customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING)
        response = self.client.get(f'/api/pay/{other_booking.customer_token}/payments/{self.payment.id}/')
        self.assertEqual(response.status_code, 404)


class StkPushCooldownTests(APITestCase):
    """A retry (e.g. after the frontend gives up polling) shouldn't be able to fire a second
    concurrent STK push while the first one might still complete - that's how a customer ends
    up paying twice with nothing catching it."""

    def setUp(self):
        driver = Driver.objects.create(full_name='Cooldown Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='cooldown-client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=driver, status=BookingStatus.PENDING)

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_a_second_push_within_the_cooldown_is_rejected(self, mock_stk):
        mock_stk.return_value = {'CheckoutRequestID': 'ws_CO_1'}
        initiate_stk_push_payment(self.booking, '254700000000', self.booking.deposit_amount)

        with self.assertRaises(PaymentValidationError):
            initiate_stk_push_payment(self.booking, '254700000000', self.booking.deposit_amount)
        self.assertEqual(mock_stk.call_count, 1)

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_a_push_is_allowed_again_once_the_pending_one_is_marked_failed(self, mock_stk):
        mock_stk.return_value = {'CheckoutRequestID': 'ws_CO_1'}
        payment, _ = initiate_stk_push_payment(self.booking, '254700000000', self.booking.deposit_amount)
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=['status'])

        initiate_stk_push_payment(self.booking, '254700000000', self.booking.deposit_amount)
        self.assertEqual(mock_stk.call_count, 2)

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_a_push_is_allowed_again_after_the_cooldown_window_passes(self, mock_stk):
        mock_stk.return_value = {'CheckoutRequestID': 'ws_CO_1'}
        payment, _ = initiate_stk_push_payment(self.booking, '254700000000', self.booking.deposit_amount)
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=5))

        initiate_stk_push_payment(self.booking, '254700000000', self.booking.deposit_amount)
        self.assertEqual(mock_stk.call_count, 2)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.PENDING)
