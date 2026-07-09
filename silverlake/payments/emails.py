from core.email_utils import send_branded_email


def send_cash_payment_recorded_email(payment):
    """Sent the moment a driver records a cash payment - the customer didn't initiate this
    themselves, so this is their one independent check: if they never actually paid, this
    email is what tips them off to dispute it. Swallowed silently on failure so a
    misconfigured SMTP server never blocks the payment from being recorded."""
    booking = payment.booking
    if not booking.customer_email:
        return
    try:
        send_branded_email(
            subject=f'Cash payment recorded on your SilverLake booking #{booking.pk}',
            template_name='emails/cash_payment_recorded.html',
            context={
                'first_name': booking.customer_name.split()[0],
                'amount': f'{payment.amount:,.2f}',
                'driver_name': payment.recorded_by_driver.full_name if payment.recorded_by_driver else 'your driver',
                'booking_id': booking.pk,
                'balance_due': f'{booking.balance_due:,.2f}',
            },
            recipient_list=[booking.customer_email],
        )
    except Exception:
        pass


def send_refund_issued_email(refund):
    """Sent when an admin marks a refund as issued - previously the customer's only signal
    that money actually came back was checking their own M-Pesa/bank statement and guessing.
    Swallowed silently on failure so a misconfigured SMTP server never blocks the refund from
    being marked issued."""
    booking = refund.booking
    if not booking.customer_email:
        return
    try:
        send_branded_email(
            subject=f'Your refund has been issued — SilverLake booking #{booking.pk}',
            template_name='emails/refund_issued.html',
            context={
                'first_name': booking.customer_name.split()[0],
                'amount': f'{refund.amount:,.2f}',
                'booking_id': booking.pk,
                'reference': refund.reference,
            },
            recipient_list=[booking.customer_email],
        )
    except Exception:
        pass


def send_payout_paid_email(payout):
    """Sent when a driver-partner's payout is marked paid - their one confirmation/receipt that
    the money actually went out, beyond checking their own account. No-ops if the driver has no
    email on file; swallowed silently on failure so a misconfigured SMTP server never blocks the
    payout from being marked paid."""
    driver = payout.driver
    if not driver.email:
        return
    booking = payout.booking
    try:
        send_branded_email(
            subject=f'Your payout has been paid — SilverLake booking #{booking.pk}',
            template_name='emails/payout_paid.html',
            context={
                'first_name': driver.full_name.split()[0],
                'amount': f'{payout.amount:,.2f}',
                'booking_id': booking.pk,
                'customer_name': booking.customer_name,
                'reference': payout.payout_reference,
            },
            recipient_list=[driver.email],
        )
    except Exception:
        pass


def send_cash_payment_driver_confirmation_email(payment):
    """Confirms to the driver themselves that their recorded cash payment went through, and
    sets expectations that it needs admin verification before their payout is released. Swallowed
    silently on failure so a misconfigured SMTP server never blocks the payment from being
    recorded."""
    driver = payment.recorded_by_driver
    booking = payment.booking
    if not driver or not driver.email:
        return
    try:
        send_branded_email(
            subject=f'Cash payment recorded — SilverLake booking #{booking.pk}',
            template_name='emails/cash_payment_driver_confirmation.html',
            context={
                'first_name': driver.full_name.split()[0],
                'amount': f'{payment.amount:,.2f}',
                'customer_name': booking.customer_name,
                'booking_id': booking.pk,
                'balance_due': f'{booking.balance_due:,.2f}',
            },
            recipient_list=[driver.email],
        )
    except Exception:
        pass
