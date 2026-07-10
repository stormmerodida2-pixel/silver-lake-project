import uuid
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from bookings.models import BookingStatus
from bookings.tests import make_booking, make_vehicle
from drivers.models import Driver

from .models import DriverPayout, Payment, PaymentMethod, PaymentStatus
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


class DjangoAdminPayoutActionTests(APITestCase):
    """The Django admin's own bulk action used to bypass the cash-payout verification gate
    entirely - it called payout.mark_paid() directly with no check at all. Tests the
    ModelAdmin action directly (rather than via the /admin/ URL) since that URL is only
    registered when DEBUG is on, and Django's test runner always forces DEBUG off."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        from .admin import DriverPayoutAdmin

        self.superadmin = User.objects.create_superuser(username='django-admin-super@example.com', password='pass12345!')
        driver = Driver.objects.create(full_name='Django Admin Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='django-admin-client@example.com', password='pass12345!')
        booking = make_booking(customer, vehicle, driver=driver, status=BookingStatus.PENDING)
        Payment.objects.create(
            booking=booking, method=PaymentMethod.CASH, amount=booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        booking.confirm_if_deposit_met()
        self.payout = DriverPayout.objects.get(booking=booking)
        assert self.payout.needs_verification and not self.payout.is_verified

        self.admin = DriverPayoutAdmin(DriverPayout, AdminSite())
        request = RequestFactory().post('/admin/payments/driverpayout/')
        request.user = self.superadmin
        request.session = {}
        request._messages = FallbackStorage(request)
        self.request = request

    def test_bulk_action_does_not_pay_out_an_unverified_cash_sourced_payout(self):
        self.admin.mark_as_paid(self.request, DriverPayout.objects.filter(pk=self.payout.pk))
        self.payout.refresh_from_db()
        self.assertFalse(self.payout.is_paid)

    def test_bulk_action_still_pays_out_a_verified_payout(self):
        self.payout.verify('Confirmed with customer.')
        self.admin.mark_as_paid(self.request, DriverPayout.objects.filter(pk=self.payout.pk))
        self.payout.refresh_from_db()
        self.assertTrue(self.payout.is_paid)


class DisputeCashPaymentTests(APITestCase):
    """The one independent check a customer has on a driver's self-reported cash payment -
    reached via the no-login link in their cash_payment_recorded email, same customer_token
    mechanism as the payment page itself."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Dispute Driver', is_active=True)
        vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='dispute-client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=self.driver, status=BookingStatus.PENDING)
        self.cash_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )
        self.booking.confirm_if_deposit_met()
        self.payout = DriverPayout.objects.get(booking=self.booking)

    def _url(self, payment=None):
        payment = payment or self.cash_payment
        return f'/api/pay/{self.booking.customer_token}/payments/{payment.id}/dispute/'

    def test_can_view_the_payment_before_disputing(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_disputed'])

    def test_filing_a_dispute_flags_the_payment(self):
        response = self.client.post(self._url(), {'note': 'I never paid this.'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.cash_payment.refresh_from_db()
        self.assertTrue(self.cash_payment.is_disputed)
        self.assertIsNotNone(self.cash_payment.disputed_at)
        self.assertEqual(self.cash_payment.dispute_note, 'I never paid this.')

    def test_filing_a_dispute_relocks_an_already_verified_payout(self):
        self.payout.verify('Confirmed with customer (turned out to be wrong).')
        self.assertTrue(self.payout.is_verified)

        self.client.post(self._url(), {'note': 'Actually never paid.'}, format='json')

        self.payout.refresh_from_db()
        self.assertTrue(self.payout.needs_verification)
        self.assertFalse(self.payout.is_verified)

    def test_cannot_dispute_a_payout_already_paid_out(self):
        self.payout.verify('Confirmed.')
        self.payout.mark_paid()
        self.client.post(self._url(), {'note': 'Too late, disputing anyway.'}, format='json')
        self.payout.refresh_from_db()
        self.assertTrue(self.payout.is_paid)
        self.assertTrue(self.payout.is_verified)  # left untouched - already disbursed

    def test_only_cash_payments_can_be_disputed(self):
        mpesa_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA, amount=Decimal('100'),
            status=PaymentStatus.SUCCESSFUL,
        )
        response = self.client.post(self._url(mpesa_payment), {'note': 'Not mine.'}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_wrong_token_is_a_404(self):
        response = self.client.get(f'/api/pay/{uuid.uuid4()}/payments/{self.cash_payment.id}/dispute/')
        self.assertEqual(response.status_code, 404)

    def test_payment_belonging_to_a_different_booking_is_a_404(self):
        other_customer = User.objects.create_user(username='other-dispute@example.com', password='pass12345!')
        other_vehicle = make_vehicle(name='Other Car', price_per_day=Decimal('1000'))
        other_booking = make_booking(other_customer, other_vehicle, status=BookingStatus.PENDING)
        response = self.client.get(f'/api/pay/{other_booking.customer_token}/payments/{self.cash_payment.id}/dispute/')
        self.assertEqual(response.status_code, 404)


class ClientDeclareCashPaymentTests(APITestCase):
    """The client themselves declaring they're paying in cash, from the same no-login page used
    for M-Pesa - the self-service equivalent of a driver typing the amount on the client's
    behalf. Only records what the client says they're paying; the driver still has to separately
    confirm it was actually received before it counts toward the balance."""

    def setUp(self):
        self.driver = Driver.objects.create(user=User.objects.create_user(
            username='declare-driver@example.com', password='pass12345!',
        ), full_name='Declare Driver', is_active=True)
        vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='declare-client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=self.driver, status=BookingStatus.PENDING)

    def _url(self, booking=None):
        return f'/api/pay/{(booking or self.booking).customer_token}/declare-cash/'

    def test_client_can_declare_a_cash_payment(self):
        response = self.client.post(self._url(), {'amount': str(self.booking.deposit_amount)}, format='json')
        self.assertEqual(response.status_code, 201)

        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.method, PaymentMethod.CASH)
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertEqual(payment.recorded_by_driver_id, self.driver.id)
        self.assertEqual(Decimal(str(payment.amount)), self.booking.deposit_amount)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.PENDING)  # not confirmed until the driver confirms

    def test_declared_payment_appears_as_pending_on_the_pay_page(self):
        self.client.post(self._url(), {'amount': str(self.booking.deposit_amount)}, format='json')
        response = self.client.get(f'/api/pay/{self.booking.customer_token}/')
        pending = response.json()['pending_payments']
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['method'], 'cash')

    def test_driver_can_then_confirm_the_clients_declared_payment(self):
        self.client.post(self._url(), {'amount': str(self.booking.total_amount)}, format='json')
        payment = Payment.objects.get(booking=self.booking)

        driver_client = APIClient()
        driver_client.force_authenticate(user=self.driver.user)
        response = driver_client.post(f'/api/driver/payments/{payment.id}/confirm/')
        self.assertEqual(response.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.SUCCESSFUL)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CONFIRMED)

    def test_cannot_declare_cash_on_a_booking_with_no_driver(self):
        other_customer = User.objects.create_user(username='no-driver-client@example.com', password='pass12345!')
        other_vehicle = make_vehicle(name='No Driver Car', price_per_day=Decimal('1000'))
        other_booking = make_booking(other_customer, other_vehicle, status=BookingStatus.PENDING)
        response = self.client.post(self._url(other_booking), {'amount': '100'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=other_booking).exists())

    def test_cannot_declare_an_amount_exceeding_the_balance_due(self):
        response = self.client.post(
            self._url(), {'amount': str(self.booking.total_amount + 1)}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_cannot_declare_a_zero_or_negative_amount(self):
        for bad_amount in ('0', '-500'):
            response = self.client.post(self._url(), {'amount': bad_amount}, format='json')
            self.assertEqual(response.status_code, 400, f'amount={bad_amount} should have been rejected')
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_wrong_token_is_a_404(self):
        response = self.client.post(
            f'/api/pay/{uuid.uuid4()}/declare-cash/', {'amount': '100'}, format='json',
        )
        self.assertEqual(response.status_code, 404)
