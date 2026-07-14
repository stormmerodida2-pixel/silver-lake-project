import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.db import OperationalError, transaction
from django.db.models import Sum
from django.utils import timezone

from bookings.models import Booking, BookingStatus

from . import mpesa
from .models import CashDeposit, Payment, PaymentMethod, PaymentStatus

logger = logging.getLogger(__name__)

# Shown to the caller when the SQLite write-lock forced below (see _lock_booking) can't be
# acquired before the database's own timeout - a concurrent request is mid-transaction against
# the same booking right now, so this one should just be retried rather than failing outright.
CONCURRENT_UPDATE_MESSAGE = 'This booking is being updated by another request right now. Please try again.'

# A real STK Push either resolves - via Safaricom's callback - within seconds of the customer
# approving or dismissing the prompt on their phone, or never resolves at all because they let it
# time out. There's no in-between, so a payment still PENDING this long after being created is
# practically certain to have been abandoned, not genuinely still in flight - this project has no
# Safaricom Initiator credentials for the Transaction Status Query API that would let us ask
# instead of inferring it from elapsed time. Used to stop excluding a dead STK push from
# _pending_payments_total, so it can't permanently block the customer from paying the same
# balance another way; payments.management.commands.expire_stale_mpesa_payments uses the same
# threshold to actually mark these FAILED rather than leaving them stuck PENDING forever.
STALE_MPESA_PENDING_THRESHOLD = timedelta(minutes=5)


def expire_stale_mpesa_payments():
    """Marks PENDING M-Pesa payments older than STALE_MPESA_PENDING_THRESHOLD as FAILED - the
    actual data-hygiene counterpart to that threshold already being excluded from
    _pending_payments_total (see that constant's own docstring for why elapsed time is the only
    signal available). Shared by the expire_stale_mpesa_payments management command (for anyone
    who wants to run this by hand, or via an external cron/Task Scheduler entry) and
    payments.scheduler's in-process background sweep (see that module for why this project runs
    it automatically rather than requiring one)."""
    cutoff = timezone.now() - STALE_MPESA_PENDING_THRESHOLD
    return Payment.objects.filter(
        method=PaymentMethod.MPESA, status=PaymentStatus.PENDING, created_at__lt=cutoff,
    ).update(status=PaymentStatus.FAILED)


# Mirrors payments.views.REMINDER_COOLDOWN - kept as its own constant rather than imported from
# there, since payments.views already imports from this module and importing back would be
# circular. Long enough that an automated nudge isn't spam, short enough a driver who genuinely
# forgot can be re-poked the same day - same reasoning as the manual Remind buttons, since this
# reuses their exact cooldown fields.
AUTO_REMINDER_COOLDOWN = timedelta(hours=1)

# How many days past a booking's scheduled end date (see Booking.needs_attention) an unresolved
# payment/deposit issue is allowed to sit before staff get pulled in directly - long enough that
# the automated driver nudges above have had a real chance to work, short enough that a booking
# genuinely isn't just quietly forgotten about for a week.
ESCALATE_AFTER = timedelta(days=3)

# How long a driver has, after confirming they've collected cash, before the first automatic
# deposit reminder fires - long enough to actually reach an M-Pesa agent, short enough that
# collected cash doesn't just sit with the driver for days unprompted. Unlike ESCALATE_AFTER
# above, this isn't tied to the booking's end date at all (see remind_undeposited_cash) - cash
# should be deposited promptly regardless of how much of the rental period is left.
CASH_DEPOSIT_REMINDER_GRACE_PERIOD = timedelta(hours=2)


def escalate_stuck_bookings():
    """The automated counterpart to the manual Remind Driver/Remind Deposit/Remind Balance
    buttons (see payments.views.PaymentViewSet.remind/.remind_deposit,
    core.views.AdminBookingViewSet.remind_balance) - rather than relying on staff to notice a
    booking has gone quiet and click one of those, this runs on every scheduler tick (see
    payments.scheduler) and does it for them automatically once a booking is needs_attention
    (past its scheduled end date, still open - see Booking.needs_attention, which this mirrors
    exactly). Reuses the exact same reminder functions and cooldown fields the manual buttons
    use, so a recent manual reminder isn't immediately duplicated by this, and vice versa.
    (Undeposited cash is the one exception - see remind_undeposited_cash, which owns nudging the
    driver about that regardless of end_date; this function only still checks for it to decide
    whether to escalate to staff below.)

    If a booking is still unresolved ESCALATE_AFTER days past its scheduled end date, staff get a
    one-time email/notification of their own (see Booking.payment_escalated_at, which guards
    against repeating this every scheduler tick thereafter) - the automated driver nudges clearly
    aren't resolving it on their own, so a human needs to step in and chase it directly. Scoped to
    bookings with a driver assigned, same as every reminder action this reuses - a self-drive
    booking has no driver to nudge in the first place."""
    from bookings.emails import send_booking_balance_reminder_email, send_payment_escalation_staff_notification_email
    from notifications.models import NotificationEvent
    from notifications.services import notify

    from .emails import send_payment_reminder_email

    now = timezone.now()
    today = timezone.localdate()

    stuck_bookings = Booking.objects.filter(
        status__in=[BookingStatus.CONFIRMED, BookingStatus.ONGOING],
        end_date__lt=today,
        driver__isnull=False,
    ).select_related('driver', 'vehicle')

    for booking in stuck_bookings:
        reasons = []

        pending_payment = booking.payments.filter(status=PaymentStatus.PENDING).exclude(
            method=PaymentMethod.MPESA, created_at__lt=now - STALE_MPESA_PENDING_THRESHOLD,
        ).first()
        if pending_payment:
            reasons.append('A declared payment is still unconfirmed by the driver.')
            if not pending_payment.last_reminded_at or now - pending_payment.last_reminded_at >= AUTO_REMINDER_COOLDOWN:
                pending_payment.last_reminded_at = now
                pending_payment.save(update_fields=['last_reminded_at'])
                send_payment_reminder_email(pending_payment)
                notify(
                    NotificationEvent.PAYMENT_REMINDER,
                    f'Please confirm the {pending_payment.get_method_display()} payment you declared',
                    driver=pending_payment.recorded_by_driver, link_path='/driver',
                )

        # Reminding the driver is remind_undeposited_cash's job now (runs independently of
        # end_date, so it starts nudging well before a booking is even overdue) - this only
        # still needs to know *whether* cash is undeposited, to fold it into staff escalation
        # below once the booking itself is stuck.
        if booking.payments.filter(
            method=PaymentMethod.CASH, status=PaymentStatus.SUCCESSFUL, cash_deposit__isnull=True,
        ).exists():
            reasons.append('Cash was collected but has not been deposited into the Paybill.')

        if booking.balance_due > 0:
            reasons.append(f'KES {booking.balance_due:,.2f} is still owed on this booking.')
            if not booking.last_balance_reminder_at or now - booking.last_balance_reminder_at >= AUTO_REMINDER_COOLDOWN:
                booking.last_balance_reminder_at = now
                booking.save(update_fields=['last_balance_reminder_at'])
                send_booking_balance_reminder_email(booking)

        if reasons and not booking.payment_escalated_at and today - booking.end_date >= ESCALATE_AFTER:
            send_payment_escalation_staff_notification_email(booking, reasons)
            booking.payment_escalated_at = now
            booking.save(update_fields=['payment_escalated_at'])
            notify(
                NotificationEvent.PAYMENT_ESCALATED,
                f'Booking #{booking.pk} has an unresolved payment issue {ESCALATE_AFTER.days}+ days after its scheduled return',
                organization=booking.vehicle.owner, link_path='/admin/bookings',
            )


def remind_undeposited_cash():
    """Nudges a driver about cash they've confirmed collecting but not yet deposited into the
    Paybill - runs on every scheduler tick (see payments.scheduler), independent of whether the
    booking's trip has ended yet. escalate_stuck_bookings only starts caring about a booking once
    it's past its scheduled end date, which left a real gap: a driver could sit on cash collected
    on day one of a five-day rental with zero automated nudge until day five. This is the earlier,
    driver-facing half of that same concern - it runs for every undeposited cash payment, not
    just ones already overdue, and is the sole sender of this reminder (escalate_stuck_bookings
    still checks whether cash is undeposited, but only to decide whether to escalate to staff).

    Waits CASH_DEPOSIT_REMINDER_GRACE_PERIOD after the payment was confirmed before the first
    reminder, so a driver isn't nagged the instant they record it - they need real time to reach
    an agent. Re-reminds on AUTO_REMINDER_COOLDOWN thereafter, the same cooldown field/rate the
    manual Remind Deposit button and escalate_stuck_bookings both already use, so none of these
    ever duplicate each other within the same window."""
    from notifications.models import NotificationEvent
    from notifications.services import notify

    from .emails import send_cash_deposit_reminder_email

    now = timezone.now()
    cutoff = now - CASH_DEPOSIT_REMINDER_GRACE_PERIOD

    undeposited = Payment.objects.filter(
        method=PaymentMethod.CASH, status=PaymentStatus.SUCCESSFUL,
        cash_deposit__isnull=True, created_at__lt=cutoff,
    ).select_related('recorded_by_driver')

    for payment in undeposited:
        if payment.last_reminded_at and now - payment.last_reminded_at < AUTO_REMINDER_COOLDOWN:
            continue
        payment.last_reminded_at = now
        payment.save(update_fields=['last_reminded_at'])
        send_cash_deposit_reminder_email(payment)
        notify(
            NotificationEvent.CASH_DEPOSIT_REMINDER, 'Please redeposit the cash you collected into the Paybill',
            driver=payment.recorded_by_driver, link_path='/driver',
        )


def _lock_booking(booking):
    """Forces a real write against the booking row as the first statement in the caller's
    transaction - select_for_update() would be the standard way to serialize concurrent requests
    against the same booking, but it's a documented no-op on SQLite (this project's current
    database; see BookingViewSet.create for the same technique used against double-booking a
    vehicle). SQLite acquires a database-level write lock on the first write in a transaction, so
    a second concurrent request touching a payment for this same booking has to wait for this one
    to commit or roll back before its own balance check can even run - without this, two payments
    that each individually fit the remaining balance at the moment they're created could both
    still go on to succeed, together overpaying the booking."""
    Booking.objects.filter(pk=booking.pk).update(updated_at=timezone.now())


def _pending_payments_total(booking, exclude_pk=None):
    """Sum of this booking's still-unresolved payments - money that might land at any moment but
    hasn't yet (Booking.amount_paid only counts SUCCESSFUL ones), so it has to be reserved
    against the remaining balance too. Otherwise a driver-declared cash payment sitting PENDING
    alongside a customer's own M-Pesa attempt could each pass a plain balance_due check
    individually, then both later succeed and overpay the booking.

    A stale PENDING M-Pesa payment (see STALE_MPESA_PENDING_THRESHOLD) is excluded rather than
    reserved - cash/card payments are deliberately left reserved no matter how old (a driver can
    legitimately take a while to confirm one; see PaymentViewSet.remind), but a dead STK push
    would otherwise reserve its amount forever, since nothing ever marks it FAILED on its own."""
    queryset = booking.payments.filter(status=PaymentStatus.PENDING).exclude(
        method=PaymentMethod.MPESA, created_at__lt=timezone.now() - STALE_MPESA_PENDING_THRESHOLD,
    )
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)
    return queryset.aggregate(total=Sum('amount'))['total'] or Decimal('0')


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
    if not booking.is_deposit_paid and amount < booking.deposit_amount:
        raise PaymentValidationError(f'First payment must be at least the deposit of {booking.deposit_amount}.')

    try:
        with transaction.atomic():
            _lock_booking(booking)

            available = booking.balance_due - _pending_payments_total(booking)
            if amount > available:
                raise PaymentValidationError(f'Amount exceeds the outstanding balance of {available}.')

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
    except OperationalError:
        raise PaymentValidationError(CONCURRENT_UPDATE_MESSAGE)

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
    at confirmation, so a driver can't quietly confirm less than what the client agreed to pay.

    The single entry point for declaring cash, whether it's the driver themselves (see
    bookings.views.DriverDeclarePaymentView) or the client self-declaring via the no-login
    customer_token page (see payments.views.token_declare_cash_payment) - both pass the
    booking's own driver in, so Driver.cash_payments_enabled only has to be enforced here once."""
    if method not in OFFLINE_PAYMENT_METHODS:
        raise PaymentValidationError('Only cash or card payments are declared this way - use the M-Pesa flow instead.')
    if booking.status in _CLOSED_BOOKING_STATUSES:
        raise PaymentValidationError(f'This booking is already {booking.get_status_display().lower()}.')
    if amount <= 0:
        raise PaymentValidationError('Amount must be greater than zero.')
    if method == PaymentMethod.CASH and driver is not None and not driver.cash_payments_enabled:
        raise PaymentValidationError('Cash payments are disabled for this driver - use M-Pesa instead.')

    try:
        with transaction.atomic():
            _lock_booking(booking)

            available = booking.balance_due - _pending_payments_total(booking)
            if amount > available:
                raise PaymentValidationError(f'Amount exceeds the outstanding balance of {available}.')

            return Payment.objects.create(
                booking=booking, method=method, amount=amount,
                status=PaymentStatus.PENDING, recorded_by_driver=driver, note=note,
            )
    except OperationalError:
        raise PaymentValidationError(CONCURRENT_UPDATE_MESSAGE)


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

    try:
        with transaction.atomic():
            _lock_booking(payment.booking)
            payment.refresh_from_db()

            if payment.status != PaymentStatus.PENDING:
                raise PaymentValidationError('This payment has already been confirmed, or is no longer pending.')

            # Re-check against the balance as it stands right now, not as it stood when this was
            # declared - something else (the customer's own M-Pesa payment, say) may have
            # covered it in the meantime, and confirming this on top would overpay the booking.
            booking = Booking.objects.get(pk=payment.booking_id)
            if payment.amount > booking.balance_due:
                raise PaymentValidationError(
                    f'Confirming this would overpay the booking (only KES {booking.balance_due} is still due) - '
                    'check whether the customer already paid another way before confirming.'
                )

            payment.status = PaymentStatus.SUCCESSFUL
            payment.save(update_fields=['status'])
    except OperationalError:
        raise PaymentValidationError(CONCURRENT_UPDATE_MESSAGE)

    booking.confirm_if_deposit_met()

    from .emails import (
        send_cash_payment_staff_notification_email,
        send_offline_payment_driver_confirmation_email,
        send_offline_payment_recorded_email,
    )

    send_offline_payment_recorded_email(payment)
    send_offline_payment_driver_confirmation_email(payment)

    from notifications.models import NotificationEvent
    from notifications.services import notify

    notify(
        NotificationEvent.PAYMENT_RECORDED,
        f'{payment.get_method_display()} payment of KES {payment.amount:,.2f} recorded on booking #{booking.pk}',
        user=booking.user, link_path='/account/bookings',
    )

    if payment.method == PaymentMethod.CASH:
        send_cash_payment_staff_notification_email(payment)

        notify(
            NotificationEvent.CASH_PAYMENT_RECORDED,
            f'KES {payment.amount:,.2f} cash recorded for booking #{booking.pk}',
            organization=booking.vehicle.owner, link_path='/admin/payments',
        )

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

    cash_deposit = CashDeposit.objects.create(
        payment=payment, amount=amount, mpesa_reference=mpesa_reference, logged_by=driver,
    )

    from .emails import send_cash_deposit_staff_notification_email

    send_cash_deposit_staff_notification_email(cash_deposit)

    from notifications.models import NotificationEvent
    from notifications.services import notify

    notify(
        NotificationEvent.CASH_DEPOSIT_LOGGED,
        f'KES {amount:,.2f} cash deposit logged for booking #{payment.booking_id}',
        organization=payment.booking.vehicle.owner, link_path='/admin/payouts',
    )

    return cash_deposit
