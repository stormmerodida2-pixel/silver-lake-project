import logging
from datetime import timedelta

from django.utils import timezone

from bookings.models import BookingStatus

from . import mpesa
from .models import CashDeposit, Payment, PaymentMethod, PaymentStatus

logger = logging.getLogger(__name__)


class PaymentValidationError(Exception):
    """Raised for a request that fails a business rule (wrong amount, gateway error, etc.) -
    callers turn this into a 400/502 response with the given message."""


# Bookings in these statuses are done - cancelled has nothing left to pay, completed should
# already be settled - so no new payment should ever be recorded against either.
_CLOSED_BOOKING_STATUSES = {BookingStatus.CANCELLED, BookingStatus.COMPLETED}

# How long a just-sent STK push is considered "still might complete" before we'll let the same
# booking try again - short enough that a genuinely abandoned prompt isn't stuck forever, long
# enough to stop a customer firing a second concurrent prompt (and risking paying twice) just
# because our own poll gave up waiting before Safaricom's callback arrived.
STK_PUSH_RETRY_COOLDOWN = timedelta(seconds=60)


def initiate_stk_push_payment(booking, phone_number, amount):
    """Shared by both the logged-in customer payment flow and the no-login token payment page -
    validates the amount against the booking, creates the Payment row, and kicks off the STK
    Push prompt. Raises PaymentValidationError on any failure; the Payment row it already
    created is marked FAILED before re-raising so it isn't left stuck as PENDING."""
    if booking.status in _CLOSED_BOOKING_STATUSES:
        raise PaymentValidationError(f'This booking is already {booking.get_status_display().lower()}.')
    if amount <= 0:
        raise PaymentValidationError('Amount must be greater than zero.')
    if amount > booking.balance_due:
        raise PaymentValidationError(f'Amount exceeds the outstanding balance of {booking.balance_due}.')
    if not booking.is_deposit_paid and amount < booking.deposit_amount:
        raise PaymentValidationError(f'First payment must be at least the deposit of {booking.deposit_amount}.')

    recent_pending = booking.payments.filter(
        method=PaymentMethod.MPESA, status=PaymentStatus.PENDING,
        created_at__gte=timezone.now() - STK_PUSH_RETRY_COOLDOWN,
    ).exists()
    if recent_pending:
        raise PaymentValidationError(
            'A payment request was already sent to your phone in the last minute. Please '
            'complete it, or wait a moment before trying again.'
        )

    payment = Payment.objects.create(
        booking=booking, method=PaymentMethod.MPESA, amount=amount, phone_number=phone_number,
    )

    try:
        result = mpesa.initiate_stk_push(
            phone_number=phone_number,
            amount=amount,
            account_reference=f'SILVERLAKE-{booking.pk}',
            transaction_desc='SilverLake Car Rentals booking payment',
        )
    except Exception as exc:
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=['status'])
        # Never surface the raw upstream error (e.g. a requests.HTTPError whose message
        # includes Safaricom's own API URL) to the customer - log it for us, show them
        # something they can actually act on.
        logger.exception('M-Pesa STK push failed for booking %s', booking.pk)
        raise PaymentValidationError(
            'Could not reach M-Pesa right now. Please try again shortly, or pay directly via '
            'Paybill 400400 (Account: SILVERLAKE).'
        ) from exc

    payment.mpesa_checkout_request_id = result.get('CheckoutRequestID', '')
    payment.save(update_fields=['mpesa_checkout_request_id'])
    return payment, result


def record_cash_payment(booking, amount, driver, note=''):
    """A driver reporting that a walk-up client paid in cash on the spot, instead of via M-Pesa.
    Recorded as successful immediately (there's no gateway to confirm against) - the
    recorded_by_driver field keeps an audit trail of who vouched for it, and the resulting
    driver payout is flagged for admin verification before it can be paid out (see
    Booking._ensure_driver_payout). The customer is emailed immediately as an independent
    check, since they didn't initiate this payment themselves; the driver also gets a
    confirmation of their own, so they know the payment was recorded and what happens next."""
    if booking.status in _CLOSED_BOOKING_STATUSES:
        raise PaymentValidationError(f'This booking is already {booking.get_status_display().lower()}.')
    if amount <= 0:
        raise PaymentValidationError('Amount must be greater than zero.')
    if amount > booking.balance_due:
        raise PaymentValidationError(f'Amount exceeds the outstanding balance of {booking.balance_due}.')

    payment = Payment.objects.create(
        booking=booking, method=PaymentMethod.CASH, amount=amount,
        status=PaymentStatus.SUCCESSFUL, recorded_by_driver=driver, note=note,
    )
    booking.confirm_if_deposit_met()

    from .emails import send_cash_payment_driver_confirmation_email, send_cash_payment_recorded_email

    send_cash_payment_recorded_email(payment)
    send_cash_payment_driver_confirmation_email(payment)

    return payment


def log_cash_deposit(payment, amount, mpesa_reference, driver):
    """A driver logging that they've deposited collected cash into the company Paybill -
    the second half of the cash-payment trust chain (see CashDeposit). The deposited amount can
    never be less than what was collected: this is a hard rejection, not a warning, since it's
    the one automatic check standing between a driver quietly keeping part of the cash and their
    payout still going through. A superadmin still has to cross-check mpesa_reference against
    the real Paybill statement by hand (see DriverPayout.verify) - this doesn't replace that,
    it just makes shortchanging impossible to do silently."""
    if payment.method != PaymentMethod.CASH:
        raise PaymentValidationError('Only cash payments need a deposit logged.')
    if hasattr(payment, 'cash_deposit'):
        raise PaymentValidationError('A deposit has already been logged for this payment.')
    if not mpesa_reference.strip():
        raise PaymentValidationError('The M-Pesa reference for the Paybill deposit is required.')
    if amount < payment.amount:
        raise PaymentValidationError(
            f'Deposited amount (KES {amount}) is less than the cash collected (KES {payment.amount}). '
            'The full amount collected must be deposited.'
        )

    return CashDeposit.objects.create(
        payment=payment, amount=amount, mpesa_reference=mpesa_reference.strip(), logged_by=driver,
    )
