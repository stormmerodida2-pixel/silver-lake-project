from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from bookings.models import BookingStatus
from bookings.tests import make_booking, make_vehicle
from drivers.models import Driver

from .models import Payment, PaymentMethod, PaymentStatus

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
