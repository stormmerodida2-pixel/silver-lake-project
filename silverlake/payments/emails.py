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
