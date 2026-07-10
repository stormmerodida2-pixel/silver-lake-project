import logging
import re
from datetime import timedelta

from django.utils import timezone

from bookings.models import BookingStatus

from . import mpesa
from .models import CashDeposit, Payment, PaymentMethod, PaymentStatus

logger = logging.getLogger(__name__)

# Real M-Pesa transaction codes are always exactly 10 characters, start with a letter, and
# contain only uppercase letters/digits after that (e.g. QGH7XXXXXX) - this doesn't confirm the
# code actually exists or matches the deposited amount (that needs Safaricom's Transaction
# Status Query API, which needs Initiator credentials this project doesn't have yet), but it
# does reject obviously-fake input like "asdf" or "12345" before it gets treated as a real
# reference a superadmin might later try to look up.
MPESA_REFERENCE_PATTERN = re.compile(r'^[A-Z][A-Z0-9]{9}$')


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


# Cash and card both go through the same declare-then-confirm flow, since neither has a live
# gateway confirming them the way M-Pesa's STK Push callback does - mpesa payments never use
# these, they go through initiate_stk_push_payment instead.
OFFLINE_PAYMENT_METHODS = {PaymentMethod.CASH, PaymentMethod.CARD}


def declare_offline_payment(booking, method, amount, driver, note=''):
    """A driver, with the client physically present, recording exactly how much the client says
    they're paying right now and by which offline method (cash or card). Created as PENDING, not
    SUCCESSFUL - there's no gateway to confirm a cash handoff or an in-person card tap against,
    so the amount only becomes real once the driver separately confirms it was actually received
    (see confirm_offline_payment). The amount is locked at declaration time and never re-entered
    at confirmation, so a driver can't quietly confirm less than what the client agreed to pay."""
    if method not in OFFLINE_PAYMENT_METHODS:
        raise PaymentValidationError('Only cash or card payments are declared this way - use the M-Pesa flow instead.')
    if booking.status in _CLOSED_BOOKING_STATUSES:
        raise PaymentValidationError(f'This booking is already {booking.get_status_display().lower()}.')
    if amount <= 0:
        raise PaymentValidationError('Amount must be greater than zero.')
    if amount > booking.balance_due:
        raise PaymentValidationError(f'Amount exceeds the outstanding balance of {booking.balance_due}.')

    return Payment.objects.create(
        booking=booking, method=method, amount=amount,
        status=PaymentStatus.PENDING, recorded_by_driver=driver, note=note,
    )


def confirm_offline_payment(payment):
    """The driver confirming a previously-declared cash/card payment (see
    declare_offline_payment) was actually received - takes no amount, since it was already
    locked in when declared. The customer is emailed immediately as an independent check, since
    they didn't initiate this confirmation themselves; the driver also gets one of their own.
    Cash specifically also notifies staff/superadmins directly - unlike M-Pesa or card, there's
    no transaction record anywhere else (no receipt number, no card statement) until someone at
    SilverLake actually collects the cash from the driver, so staff need their own heads-up to
    keep track of it rather than finding out only when reconciling payouts later."""
    if payment.method not in OFFLINE_PAYMENT_METHODS:
        raise PaymentValidationError('Only cash or card payments are confirmed this way.')
    if payment.status != PaymentStatus.PENDING:
        raise PaymentValidationError('This payment has already been confirmed, or is no longer pending.')

    payment.status = PaymentStatus.SUCCESSFUL
    payment.save(update_fields=['status'])
    payment.booking.confirm_if_deposit_met()

    from .emails import (
        send_cash_payment_staff_notification_email,
        send_offline_payment_driver_confirmation_email,
        send_offline_payment_recorded_email,
    )

    send_offline_payment_recorded_email(payment)
    send_offline_payment_driver_confirmation_email(payment)
    if payment.method == PaymentMethod.CASH:
        send_cash_payment_staff_notification_email(payment)

    return payment


def log_cash_deposit(payment, amount, mpesa_reference, driver):
    """A driver logging that they've deposited cash they collected (see
    confirm_offline_payment) into the company Paybill - the second half of the cash-payment
    trust chain (see CashDeposit). The deposited amount can never be less than what was
    collected: this is a hard rejection, not a warning, since it's the one automatic check
    standing between a driver quietly keeping part of the cash and their payout still going
    through. A superadmin still has to cross-check mpesa_reference against the real Paybill
    statement by hand (see AdminDriverPayoutViewSet.verify) - this doesn't replace that, it just
    makes shortchanging impossible to do silently."""
    if payment.method != PaymentMethod.CASH:
        raise PaymentValidationError('Only cash payments need a deposit logged.')
    if payment.status != PaymentStatus.SUCCESSFUL:
        raise PaymentValidationError('Only a confirmed cash payment can have a deposit logged against it.')
    if hasattr(payment, 'cash_deposit'):
        raise PaymentValidationError('A deposit has already been logged for this payment.')

    mpesa_reference = mpesa_reference.strip().upper()
    if not mpesa_reference:
        raise PaymentValidationError('The M-Pesa reference for the Paybill deposit is required.')
    if not MPESA_REFERENCE_PATTERN.match(mpesa_reference):
        raise PaymentValidationError(
            f'"{mpesa_reference}" doesn\'t look like a real M-Pesa reference (should be 10 characters, '
            'starting with a letter, e.g. QGH7XXXXXX). Check the deposit confirmation SMS and try again.'
        )
    if amount < payment.amount:
        raise PaymentValidationError(
            f'Deposited amount (KES {amount}) is less than the cash collected (KES {payment.amount}). '
            'The full amount collected must be deposited.'
        )

    return CashDeposit.objects.create(
        payment=payment, amount=amount, mpesa_reference=mpesa_reference, logged_by=driver,
    )
