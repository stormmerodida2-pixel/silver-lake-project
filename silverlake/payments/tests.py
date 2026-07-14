import sys
import uuid
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from bookings.models import BookingStatus
from bookings.tests import make_booking, make_vehicle
from core.models import StaffOrganization
from drivers.models import Driver
from fleet.models import FleetPartner

from .models import CashDeposit, DriverPayout, Payment, PaymentMethod, PaymentStatus
from .services import (
    PaymentValidationError,
    confirm_offline_payment,
    declare_offline_payment,
    initiate_stk_push_payment,
)

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

    def test_no_login_pay_page_rejects_an_expired_token(self):
        long_ago = timezone.localdate() - timedelta(days=60)
        self.booking.start_date = long_ago
        self.booking.end_date = long_ago
        self.booking.save(update_fields=['start_date', 'end_date'])
        response = self.client.get(f'/api/pay/{self.booking.customer_token}/')
        self.assertEqual(response.status_code, 404)

    def test_no_login_pay_page_works_within_the_grace_period(self):
        response = self.client.get(f'/api/pay/{self.booking.customer_token}/')
        self.assertEqual(response.status_code, 200)


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

    def test_filing_a_dispute_notifies_staff(self):
        # Email is this app's only notification channel - without this, a dispute that re-locks
        # an already-verified (or even already-paid) payout could sit unnoticed indefinitely.
        staff = User.objects.create_user(
            username='dispute-staff@example.com', email='dispute-staff@example.com',
            password='pass12345!', is_staff=True,
        )
        mail.outbox = []
        self.client.post(self._url(), {'note': 'I never paid this.'}, format='json')
        disputed_emails = [m for m in mail.outbox if 'Payment disputed' in m.subject]
        self.assertEqual(len(disputed_emails), 1)
        self.assertIn(staff.email, disputed_emails[0].bcc)

    def test_filing_a_dispute_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.post(self._url(), {'note': 'I never paid this.'}, format='json')
        notification = Notification.objects.get(event=NotificationEvent.PAYMENT_DISPUTED)
        self.assertIn(str(self.booking.id), notification.message)

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


class ResolveDisputeTests(APITestCase):
    """Staff clearing a customer's dispute once it's been investigated - the one action that
    was previously entirely missing (is_disputed could only ever be set True, never cleared).
    Requires a note, the same attested-action pattern as AdminDriverPayoutViewSet.verify."""

    def setUp(self):
        self.staff = User.objects.create_user(username='resolve-staff@example.com', password='pass12345!', is_staff=True)
        self.plain_user = User.objects.create_user(username='resolve-plain@example.com', password='pass12345!')
        self.driver = Driver.objects.create(full_name='Resolve Driver', is_active=True)
        vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='resolve-client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=self.driver, status=BookingStatus.PENDING)
        self.payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=self.booking.total_amount,
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
            is_disputed=True, disputed_at=timezone.now(), dispute_note='I never paid this.',
        )
        self.booking.confirm_if_deposit_met()
        self.payout = DriverPayout.objects.get(booking=self.booking)

    def _url(self):
        return f'/api/payments/{self.payment.id}/resolve-dispute/'

    def test_staff_can_resolve_a_dispute_with_a_note(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url(), {'note': 'Confirmed with customer - payment was received.'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertFalse(self.payment.is_disputed)
        self.assertEqual(self.payment.dispute_resolution_note, 'Confirmed with customer - payment was received.')
        self.assertIsNotNone(self.payment.dispute_resolved_at)
        # The original complaint stays on record, separate from the resolution.
        self.assertEqual(self.payment.dispute_note, 'I never paid this.')

    def test_requires_a_note(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url(), {}, format='json')
        self.assertEqual(response.status_code, 400)
        self.payment.refresh_from_db()
        self.assertTrue(self.payment.is_disputed)

    def test_cannot_resolve_a_payment_that_is_not_disputed(self):
        self.payment.is_disputed = False
        self.payment.save(update_fields=['is_disputed'])
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url(), {'note': 'Nothing to resolve.'}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_does_not_touch_the_payouts_verification_state(self):
        self.payout.verify('Confirmed before the dispute was filed.')
        self.payout.needs_verification = True
        self.payout.is_verified = False
        self.payout.save(update_fields=['needs_verification', 'is_verified'])

        self.client.force_authenticate(user=self.staff)
        self.client.post(self._url(), {'note': 'Resolved.'}, format='json')

        self.payout.refresh_from_db()
        self.assertFalse(self.payout.is_verified)  # left untouched - a separate attestation

    def test_non_staff_cannot_resolve_a_dispute(self):
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.post(self._url(), {'note': 'Trying anyway.'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.payment.refresh_from_db()
        self.assertTrue(self.payment.is_disputed)

    def test_resolving_logs_an_audit_entry(self):
        from core.models import AuditLog

        self.client.force_authenticate(user=self.staff)
        self.client.post(self._url(), {'note': 'Resolved after investigation.'}, format='json')
        entry = AuditLog.objects.get(action='payment.resolve_dispute')
        self.assertEqual(entry.detail, 'Resolved after investigation.')

    def test_resolving_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.force_authenticate(user=self.staff)
        self.client.post(self._url(), {'note': 'Resolved.'}, format='json')
        notification = Notification.objects.get(event=NotificationEvent.DISPUTE_RESOLVED)
        self.assertIn(str(self.booking.id), notification.message)


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

    def test_non_numeric_amount_is_rejected(self):
        response = self.client.post(self._url(), {'amount': 'abc'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Payment.objects.filter(booking=self.booking).exists())

    def test_wrong_token_is_a_404(self):
        response = self.client.post(
            f'/api/pay/{uuid.uuid4()}/declare-cash/', {'amount': '100'}, format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_expired_token_is_a_404(self):
        long_ago = timezone.localdate() - timedelta(days=60)
        self.booking.start_date = long_ago
        self.booking.end_date = long_ago
        self.booking.save(update_fields=['start_date', 'end_date'])
        response = self.client.post(self._url(), {'amount': '100'}, format='json')
        self.assertEqual(response.status_code, 404)


class PaymentReminderTests(APITestCase):
    """Staff can nudge a driver who's sitting on a pending (declared but unconfirmed) payment -
    the only prompt otherwise is the driver noticing it in their own portal."""

    def setUp(self):
        self.staff = User.objects.create_user(username='remind-staff@example.com', password='pass12345!', is_staff=True)
        self.superadmin = User.objects.create_superuser(username='remind-super@example.com', password='pass12345!')
        self.plain_user = User.objects.create_user(username='remind-plain@example.com', password='pass12345!')
        self.driver = Driver.objects.create(
            user=User.objects.create_user(username='remind-driver@example.com', password='pass12345!'),
            full_name='Remind Driver', is_active=True, email='remind-driver@example.com',
        )
        vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='remind-customer@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=self.driver, status=BookingStatus.PENDING)
        self.payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=Decimal('500'),
            status=PaymentStatus.PENDING, recorded_by_driver=self.driver,
        )

    def test_staff_can_remind_driver_of_a_pending_payment(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/payments/{self.payment.id}/remind/')
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertIsNotNone(self.payment.last_reminded_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('remind-driver@example.com', mail.outbox[0].to)

    def test_reminding_notifies_the_driver_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.force_authenticate(user=self.staff)
        self.client.post(f'/api/payments/{self.payment.id}/remind/')
        notification = Notification.objects.get(event=NotificationEvent.PAYMENT_REMINDER)
        self.assertEqual(notification.driver_id, self.driver.id)

    def test_cannot_remind_about_an_already_confirmed_payment(self):
        self.payment.status = PaymentStatus.SUCCESSFUL
        self.payment.save(update_fields=['status'])
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/payments/{self.payment.id}/remind/')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_cooldown_blocks_an_immediate_second_reminder(self):
        self.client.force_authenticate(user=self.staff)
        first = self.client.post(f'/api/payments/{self.payment.id}/remind/')
        self.assertEqual(first.status_code, 200)
        second = self.client.post(f'/api/payments/{self.payment.id}/remind/')
        self.assertEqual(second.status_code, 400)
        self.assertEqual(len(mail.outbox), 1)

    def test_reminder_allowed_again_once_cooldown_has_passed(self):
        self.payment.last_reminded_at = timezone.now() - timedelta(hours=2)
        self.payment.save(update_fields=['last_reminded_at'])
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/payments/{self.payment.id}/remind/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_superadmin_can_also_remind_driver(self):
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.post(f'/api/payments/{self.payment.id}/remind/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_non_staff_cannot_remind(self):
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.post(f'/api/payments/{self.payment.id}/remind/')
        self.assertEqual(response.status_code, 403)

    def test_cannot_remind_a_payment_with_no_driver(self):
        self.payment.recorded_by_driver = None
        self.payment.save(update_fields=['recorded_by_driver'])
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/payments/{self.payment.id}/remind/')
        self.assertEqual(response.status_code, 400)


class CashDepositReminderTests(APITestCase):
    """Staff can nudge a driver who's confirmed collecting cash but hasn't yet redeposited it
    into the company Paybill - distinct from PaymentReminderTests, which is about confirming
    receipt in the first place."""

    def setUp(self):
        self.staff = User.objects.create_user(username='depremind-staff@example.com', password='pass12345!', is_staff=True)
        self.plain_user = User.objects.create_user(username='depremind-plain@example.com', password='pass12345!')
        self.driver = Driver.objects.create(
            user=User.objects.create_user(username='depremind-driver@example.com', password='pass12345!'),
            full_name='DepRemind Driver', is_active=True, email='depremind-driver@example.com',
        )
        vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='depremind-customer@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=self.driver, status=BookingStatus.PENDING)
        self.payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=Decimal('500'),
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )

    def _url(self):
        return f'/api/payments/{self.payment.id}/remind-deposit/'

    def test_staff_can_remind_driver_to_deposit_cash(self):
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertIsNotNone(self.payment.last_reminded_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('depremind-driver@example.com', mail.outbox[0].to)

    def test_reminding_notifies_the_driver_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.client.force_authenticate(user=self.staff)
        self.client.post(self._url())
        notification = Notification.objects.get(event=NotificationEvent.CASH_DEPOSIT_REMINDER)
        self.assertEqual(notification.driver_id, self.driver.id)

    def test_cannot_remind_once_already_deposited(self):
        CashDeposit.objects.create(
            payment=self.payment, amount=self.payment.amount, mpesa_reference='QWE1234567', logged_by=self.driver,
        )
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_cannot_remind_about_a_pending_cash_payment(self):
        self.payment.status = PaymentStatus.PENDING
        self.payment.save(update_fields=['status'])
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(self._url())
        self.assertEqual(response.status_code, 400)

    def test_cannot_remind_about_a_card_payment(self):
        card_payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CARD, amount=Decimal('500'),
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )
        self.client.force_authenticate(user=self.staff)
        response = self.client.post(f'/api/payments/{card_payment.id}/remind-deposit/')
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


class StkPushOrgScopingTests(APITestCase):
    """Every other admin-facing endpoint resolves its booking through an org-scoped
    get_queryset(), so an org-admin never even sees another organization's data. stk_push is the
    exception - it resolves the booking straight from the request body - so it needs its own
    explicit org check to avoid letting a FleetPartner's own staff trigger a real M-Pesa charge
    attempt against a booking that isn't theirs."""

    def setUp(self):
        self.platform_staff = User.objects.create_user(username='stk-platform-staff@example.com', password='pass12345!', is_staff=True)

        self.org_a = FleetPartner.objects.create(name='STK Org A', platform_fee_percent=Decimal('10'))
        self.org_a_staff = User.objects.create_user(username='stk-org-a-staff@example.com', password='pass12345!', is_staff=True)
        StaffOrganization.objects.create(user=self.org_a_staff, organization=self.org_a)
        self.org_a_vehicle = make_vehicle(name='STK Org A Car', owner=self.org_a, is_company_owned=True, price_per_day=Decimal('1000'))

        self.org_b = FleetPartner.objects.create(name='STK Org B', platform_fee_percent=Decimal('10'))
        self.org_b_vehicle = make_vehicle(name='STK Org B Car', owner=self.org_b, is_company_owned=True, price_per_day=Decimal('1000'))

        self.customer = User.objects.create_user(username='stk-org-customer@example.com', password='pass12345!')
        self.other_customer = User.objects.create_user(username='stk-other-customer@example.com', password='pass12345!')
        self.org_a_booking = make_booking(self.customer, self.org_a_vehicle, status=BookingStatus.PENDING)
        self.org_b_booking = make_booking(self.other_customer, self.org_b_vehicle, status=BookingStatus.PENDING)

    def _post(self, booking):
        return self.client.post('/api/payments/mpesa/stk-push/', {
            'booking': booking.id, 'phone_number': '254700000000', 'amount': str(booking.deposit_amount),
        }, format='json')

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_org_admin_can_stk_push_their_own_orgs_booking(self, mock_stk):
        mock_stk.return_value = {'CheckoutRequestID': 'ws_CO_1'}
        self.client.force_authenticate(user=self.org_a_staff)
        response = self._post(self.org_a_booking)
        self.assertEqual(response.status_code, 202)

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_org_admin_cannot_stk_push_another_orgs_booking(self, mock_stk):
        self.client.force_authenticate(user=self.org_a_staff)
        response = self._post(self.org_b_booking)
        self.assertEqual(response.status_code, 403)
        mock_stk.assert_not_called()

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_platform_staff_can_stk_push_any_booking(self, mock_stk):
        mock_stk.return_value = {'CheckoutRequestID': 'ws_CO_1'}
        self.client.force_authenticate(user=self.platform_staff)
        response = self._post(self.org_a_booking)
        self.assertEqual(response.status_code, 202)

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_customer_can_stk_push_their_own_booking(self, mock_stk):
        mock_stk.return_value = {'CheckoutRequestID': 'ws_CO_1'}
        self.client.force_authenticate(user=self.customer)
        response = self._post(self.org_a_booking)
        self.assertEqual(response.status_code, 202)

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_customer_cannot_stk_push_someone_elses_booking(self, mock_stk):
        self.client.force_authenticate(user=self.customer)
        response = self._post(self.org_b_booking)
        self.assertEqual(response.status_code, 403)
        mock_stk.assert_not_called()


class OverpaymentGuardTests(APITestCase):
    """Each payment path checks its amount against the balance due at the moment it's created or
    declared, but that alone isn't enough: two payments that each individually fit the remaining
    balance can still combine to overpay the booking if both later succeed. These check that the
    still-unresolved (PENDING) amount from one path is reserved against what another path is
    allowed to ask for, and that confirming a stale declared payment re-checks the balance as it
    stands now rather than as it stood at declaration time."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Overpay Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))  # KES 7000 total (7 days)
        self.customer = User.objects.create_user(username='overpay-client@example.com', password='pass12345!')
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING)
        assert self.booking.total_amount == Decimal('7000.00')

    @patch('payments.services.mpesa.initiate_stk_push')
    def test_declared_cash_payment_reserves_balance_against_a_later_stk_push(self, mock_stk):
        # Driver declares cash for the full balance - still PENDING, not yet real money.
        declare_offline_payment(self.booking, PaymentMethod.CASH, self.booking.total_amount, driver=self.driver)

        # A customer-initiated M-Pesa push for the same balance should now be rejected: if both
        # later succeeded, the booking would be paid for twice over.
        mock_stk.return_value = {'CheckoutRequestID': 'ws_CO_1'}
        with self.assertRaises(PaymentValidationError):
            initiate_stk_push_payment(self.booking, '254700000000', self.booking.total_amount)
        mock_stk.assert_not_called()

    def test_two_declared_cash_payments_cannot_together_exceed_the_balance(self):
        declare_offline_payment(self.booking, PaymentMethod.CASH, Decimal('4000'), driver=self.driver)
        with self.assertRaises(PaymentValidationError):
            declare_offline_payment(self.booking, PaymentMethod.CASH, Decimal('4000'), driver=self.driver)

    def test_a_second_payment_is_still_allowed_once_it_fits_what_remains(self):
        declare_offline_payment(self.booking, PaymentMethod.CASH, Decimal('4000'), driver=self.driver)
        # Only KES 3000 of the KES 7000 total is still unreserved.
        declare_offline_payment(self.booking, PaymentMethod.CASH, Decimal('3000'), driver=self.driver)
        self.assertEqual(Payment.objects.filter(booking=self.booking).count(), 2)

    def test_confirming_a_stale_declared_payment_is_rejected_if_already_covered_elsewhere(self):
        cash_payment = declare_offline_payment(self.booking, PaymentMethod.CASH, self.booking.total_amount, driver=self.driver)

        # The customer pays the whole balance via M-Pesa while the cash declaration just sits
        # there unconfirmed (simulating the real STK callback landing independently).
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )

        with self.assertRaises(PaymentValidationError):
            confirm_offline_payment(cash_payment)

        cash_payment.refresh_from_db()
        self.assertEqual(cash_payment.status, PaymentStatus.PENDING)  # left untouched, not silently confirmed

    def test_confirming_the_only_pending_payment_still_works_normally(self):
        cash_payment = declare_offline_payment(self.booking, PaymentMethod.CASH, self.booking.total_amount, driver=self.driver)
        confirm_offline_payment(cash_payment)
        cash_payment.refresh_from_db()
        self.assertEqual(cash_payment.status, PaymentStatus.SUCCESSFUL)


class StaleMpesaPaymentTests(APITestCase):
    """A dead STK Push (the customer let it time out, or never approved it) never resolves on
    its own - there's no Safaricom Transaction Status Query integration to ask, so nothing ever
    marks it FAILED automatically. Without treating one as abandoned once it's clearly too old to
    still be in flight, it would permanently reserve its amount against the booking's balance
    (see OverpaymentGuardTests) and block the customer from paying any other way."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Stale Driver', is_active=True)
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))  # KES 7000 total
        self.customer = User.objects.create_user(username='stale-client@example.com', password='pass12345!')
        self.booking = make_booking(self.customer, self.vehicle, driver=self.driver, status=BookingStatus.PENDING)

    def _make_stale_mpesa_pending(self, amount):
        payment = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA, amount=amount, status=PaymentStatus.PENDING,
        )
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(minutes=10))
        return payment

    def test_a_stale_pending_mpesa_payment_does_not_block_a_new_declare(self):
        self._make_stale_mpesa_pending(self.booking.total_amount)
        # Should succeed - the stale PENDING mpesa payment is treated as abandoned, not reserved.
        declare_offline_payment(self.booking, PaymentMethod.CASH, self.booking.total_amount, driver=self.driver)
        self.assertEqual(Payment.objects.filter(booking=self.booking, status=PaymentStatus.PENDING).count(), 2)

    def test_a_fresh_pending_mpesa_payment_still_blocks(self):
        Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA,
            amount=self.booking.total_amount, status=PaymentStatus.PENDING,
        )
        with self.assertRaises(PaymentValidationError):
            declare_offline_payment(self.booking, PaymentMethod.CASH, self.booking.total_amount, driver=self.driver)

    def test_a_stale_pending_cash_payment_still_blocks(self):
        # Cash/card intentionally stay reserved no matter how old - a driver can legitimately
        # take a while to confirm one (see PaymentViewSet.remind), unlike a dead STK push.
        payment = declare_offline_payment(self.booking, PaymentMethod.CASH, self.booking.total_amount, driver=self.driver)
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=6))
        with self.assertRaises(PaymentValidationError):
            declare_offline_payment(self.booking, PaymentMethod.CARD, self.booking.total_amount, driver=self.driver)


class ExpireStaleMpesaPaymentsCommandTests(APITestCase):
    """The management command that actually flips a stale PENDING M-Pesa payment to FAILED,
    since nothing else ever will without a Safaricom Transaction Status Query integration - now
    run automatically by payments.scheduler's background sweep (see SchedulerTests), but this
    command remains available for an immediate one-off run."""

    def setUp(self):
        driver = Driver.objects.create(full_name='Command Driver', is_active=True)
        vehicle = make_vehicle(driver=driver, price_per_day=Decimal('1000'))
        customer = User.objects.create_user(username='command-client@example.com', password='pass12345!')
        self.booking = make_booking(customer, vehicle, driver=driver, status=BookingStatus.PENDING)

        self.stale_mpesa = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA, amount=Decimal('1000'), status=PaymentStatus.PENDING,
        )
        Payment.objects.filter(pk=self.stale_mpesa.pk).update(created_at=timezone.now() - timedelta(minutes=10))

        self.fresh_mpesa = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.MPESA, amount=Decimal('1000'), status=PaymentStatus.PENDING,
        )
        self.stale_cash = Payment.objects.create(
            booking=self.booking, method=PaymentMethod.CASH, amount=Decimal('1000'),
            status=PaymentStatus.PENDING, recorded_by_driver=driver,
        )
        Payment.objects.filter(pk=self.stale_cash.pk).update(created_at=timezone.now() - timedelta(minutes=10))

    def test_marks_only_stale_pending_mpesa_payments_as_failed(self):
        from io import StringIO

        from django.core.management import call_command

        call_command('expire_stale_mpesa_payments', stdout=StringIO())

        self.stale_mpesa.refresh_from_db()
        self.fresh_mpesa.refresh_from_db()
        self.stale_cash.refresh_from_db()
        self.assertEqual(self.stale_mpesa.status, PaymentStatus.FAILED)
        self.assertEqual(self.fresh_mpesa.status, PaymentStatus.PENDING)
        self.assertEqual(self.stale_cash.status, PaymentStatus.PENDING)

    def test_shared_service_function_does_the_same_thing(self):
        # payments.scheduler's background sweep calls this directly, bypassing the management
        # command wrapper entirely - confirm it alone has the exact same effect.
        from payments.services import expire_stale_mpesa_payments

        count = expire_stale_mpesa_payments()
        self.assertEqual(count, 1)

        self.stale_mpesa.refresh_from_db()
        self.fresh_mpesa.refresh_from_db()
        self.assertEqual(self.stale_mpesa.status, PaymentStatus.FAILED)
        self.assertEqual(self.fresh_mpesa.status, PaymentStatus.PENDING)


class SchedulerTests(TestCase):
    """payments.scheduler.start() runs a background sweep automatically instead of requiring an
    external cron/Task Scheduler entry - these only cover the guard logic (_should_run), never
    the actual thread/sleep loop, since that's not something a fast unit test should wait on."""

    def _should_run_with_argv(self, argv, run_main=None):
        import os

        from payments import scheduler

        old_argv, old_run_main = sys.argv, os.environ.get('RUN_MAIN')
        sys.argv = argv
        if run_main is None:
            os.environ.pop('RUN_MAIN', None)
        else:
            os.environ['RUN_MAIN'] = run_main
        try:
            return scheduler._should_run()
        finally:
            sys.argv = old_argv
            if old_run_main is None:
                os.environ.pop('RUN_MAIN', None)
            else:
                os.environ['RUN_MAIN'] = old_run_main

    def test_does_not_run_under_test(self):
        self.assertFalse(self._should_run_with_argv(['manage.py', 'test']))

    def test_does_not_run_under_migrate_or_shell(self):
        self.assertFalse(self._should_run_with_argv(['manage.py', 'migrate']))
        self.assertFalse(self._should_run_with_argv(['manage.py', 'shell']))

    def test_does_not_run_under_runserver_before_the_autoreload_worker_forks(self):
        self.assertFalse(self._should_run_with_argv(['manage.py', 'runserver']))

    def test_runs_under_runserver_once_run_main_is_set(self):
        self.assertTrue(self._should_run_with_argv(['manage.py', 'runserver'], run_main='true'))

    def test_runs_for_a_production_wsgi_entrypoint(self):
        # gunicorn/uwsgi don't go through manage.py at all, so argv won't match any known
        # subcommand - this should default to "yes, start it".
        self.assertTrue(self._should_run_with_argv(['/usr/bin/gunicorn', 'silverlake.wsgi']))

    def test_start_is_idempotent(self):
        from payments import scheduler

        original_started = scheduler._started
        try:
            scheduler._started = True  # simulate an already-started sweep
            scheduler.start()  # must not raise or start a second thread
        finally:
            scheduler._started = original_started


class EscalateStuckBookingsTests(APITestCase):
    """The automated counterpart to the manual Remind Driver/Remind Deposit/Remind Balance
    buttons - a booking past its scheduled end date with an unresolved payment/deposit issue
    gets auto-reminded (and, after long enough, staff get pulled in directly), without anyone
    having to notice and click a button."""

    def setUp(self):
        self.driver = Driver.objects.create(full_name='Escalation Driver', is_active=True, email='escalation-driver@example.com')
        self.vehicle = make_vehicle(driver=self.driver, price_per_day=Decimal('1000'))
        self.customer = User.objects.create_user(username='escalation-client@example.com', password='pass12345!')
        self.overdue_booking = make_booking(
            self.customer, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
            start_date=timezone.localdate() - timedelta(days=5), end_date=timezone.localdate() - timedelta(days=1),
        )

    def _run(self):
        from payments.services import escalate_stuck_bookings

        escalate_stuck_bookings()

    def test_a_stale_pending_payment_gets_an_automatic_reminder(self):
        payment = Payment.objects.create(
            booking=self.overdue_booking, method=PaymentMethod.CASH, amount=Decimal('1000'),
            status=PaymentStatus.PENDING, recorded_by_driver=self.driver,
        )
        mail.outbox = []
        self._run()
        payment.refresh_from_db()
        self.assertIsNotNone(payment.last_reminded_at)
        self.assertTrue(any('confirm a' in m.subject.lower() for m in mail.outbox))

    def test_undeposited_cash_gets_an_automatic_deposit_reminder(self):
        payment = Payment.objects.create(
            booking=self.overdue_booking, method=PaymentMethod.CASH, amount=Decimal('1000'),
            status=PaymentStatus.SUCCESSFUL, recorded_by_driver=self.driver,
        )
        mail.outbox = []
        self._run()
        payment.refresh_from_db()
        self.assertIsNotNone(payment.last_reminded_at)
        self.assertTrue(any('deposit cash to paybill' in m.subject.lower() for m in mail.outbox))

    def test_an_outstanding_balance_with_nothing_declared_gets_a_balance_reminder(self):
        mail.outbox = []
        self._run()
        self.overdue_booking.refresh_from_db()
        self.assertIsNotNone(self.overdue_booking.last_balance_reminder_at)
        self.assertTrue(any('outstanding balance' in m.subject.lower() for m in mail.outbox))

    def test_reminder_cooldown_prevents_an_immediate_second_auto_reminder(self):
        self.overdue_booking.last_balance_reminder_at = timezone.now()
        self.overdue_booking.save(update_fields=['last_balance_reminder_at'])
        mail.outbox = []
        self._run()
        self.assertEqual(len(mail.outbox), 0)

    def test_a_booking_not_yet_overdue_is_left_alone(self):
        booking = make_booking(
            self.customer, self.vehicle, driver=self.driver, status=BookingStatus.CONFIRMED,
        )
        mail.outbox = []
        self._run()
        booking.refresh_from_db()
        self.assertIsNone(booking.last_balance_reminder_at)

    def test_a_booking_with_no_driver_is_left_alone(self):
        from bookings.models import ServiceType

        # WITH_DRIVER (make_booking's default) auto-fills the vehicle's own driver on save() if
        # none is given (see Booking._apply_default_driver) - SELF_DRIVE is the only way to get a
        # genuinely driver-less booking on a vehicle that has one assigned.
        self_drive_booking = make_booking(
            self.customer, self.vehicle, status=BookingStatus.CONFIRMED, service_type=ServiceType.SELF_DRIVE,
            start_date=timezone.localdate() - timedelta(days=5), end_date=timezone.localdate() - timedelta(days=1),
        )
        mail.outbox = []
        self._run()
        self_drive_booking.refresh_from_db()
        self.assertIsNone(self_drive_booking.last_balance_reminder_at)

    def test_a_fully_paid_booking_needing_only_a_trip_confirmation_is_not_touched(self):
        # Fully paid, nobody clicked End Trip - this is a trip-lifecycle nudge, not a payment
        # one, so the escalation sweep (specifically about money) should do nothing here.
        Payment.objects.create(
            booking=self.overdue_booking, method=PaymentMethod.MPESA,
            amount=self.overdue_booking.total_amount, status=PaymentStatus.SUCCESSFUL,
        )
        mail.outbox = []
        self._run()
        self.overdue_booking.refresh_from_db()
        self.assertIsNone(self.overdue_booking.last_balance_reminder_at)
        self.assertIsNone(self.overdue_booking.payment_escalated_at)

    def test_does_not_escalate_to_staff_before_the_threshold(self):
        staff = User.objects.create_user(username='escalation-staff@example.com', email='escalation-staff@example.com', password='pass12345!', is_staff=True)
        mail.outbox = []
        self._run()
        self.overdue_booking.refresh_from_db()
        self.assertIsNone(self.overdue_booking.payment_escalated_at)
        self.assertFalse(any('needs attention' in m.subject.lower() for m in mail.outbox))

    def test_escalates_to_staff_once_past_the_threshold(self):
        staff = User.objects.create_user(username='escalation-staff2@example.com', email='escalation-staff2@example.com', password='pass12345!', is_staff=True)
        self.overdue_booking.start_date = timezone.localdate() - timedelta(days=10)
        self.overdue_booking.end_date = timezone.localdate() - timedelta(days=4)
        self.overdue_booking.save(update_fields=['start_date', 'end_date'])

        mail.outbox = []
        self._run()
        self.overdue_booking.refresh_from_db()
        self.assertIsNotNone(self.overdue_booking.payment_escalated_at)
        staff_emails = [m for m in mail.outbox if 'needs attention' in m.subject.lower()]
        self.assertEqual(len(staff_emails), 1)
        self.assertIn(staff.email, staff_emails[0].bcc)

    def test_escalation_notifies_admins_in_app(self):
        from notifications.models import Notification, NotificationEvent

        self.overdue_booking.start_date = timezone.localdate() - timedelta(days=10)
        self.overdue_booking.end_date = timezone.localdate() - timedelta(days=4)
        self.overdue_booking.save(update_fields=['start_date', 'end_date'])

        self._run()
        notification = Notification.objects.get(event=NotificationEvent.PAYMENT_ESCALATED)
        self.assertIn(str(self.overdue_booking.id), notification.message)

    def test_escalation_only_ever_fires_once(self):
        self.overdue_booking.start_date = timezone.localdate() - timedelta(days=10)
        self.overdue_booking.end_date = timezone.localdate() - timedelta(days=4)
        self.overdue_booking.save(update_fields=['start_date', 'end_date'])

        self._run()
        mail.outbox = []
        self._run()
        self.assertFalse(any('needs attention' in m.subject.lower() for m in mail.outbox))
