from . import mpesa
from .models import Payment, PaymentMethod, PaymentStatus


class PaymentValidationError(Exception):
    """Raised for a request that fails a business rule (wrong amount, gateway error, etc.) -
    callers turn this into a 400/502 response with the given message."""


def initiate_stk_push_payment(booking, phone_number, amount):
    """Shared by both the logged-in customer payment flow and the no-login token payment page -
    validates the amount against the booking, creates the Payment row, and kicks off the STK
    Push prompt. Raises PaymentValidationError on any failure; the Payment row it already
    created is marked FAILED before re-raising so it isn't left stuck as PENDING."""
    if amount > booking.balance_due:
        raise PaymentValidationError(f'Amount exceeds the outstanding balance of {booking.balance_due}.')
    if not booking.is_deposit_paid and amount < booking.deposit_amount:
        raise PaymentValidationError(f'First payment must be at least the deposit of {booking.deposit_amount}.')

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
        raise PaymentValidationError(str(exc)) from exc

    payment.mpesa_checkout_request_id = result.get('CheckoutRequestID', '')
    payment.save(update_fields=['mpesa_checkout_request_id'])
    return payment, result


def record_cash_payment(booking, amount, driver, note=''):
    """A driver reporting that a walk-up client paid in cash on the spot, instead of via M-Pesa.
    Recorded as successful immediately (there's no gateway to confirm against) - the
    recorded_by_driver field keeps an audit trail of who vouched for it."""
    if amount > booking.balance_due:
        raise PaymentValidationError(f'Amount exceeds the outstanding balance of {booking.balance_due}.')

    payment = Payment.objects.create(
        booking=booking, method=PaymentMethod.CASH, amount=amount,
        status=PaymentStatus.SUCCESSFUL, recorded_by_driver=driver, note=note,
    )
    booking.confirm_if_deposit_met()
    return payment
