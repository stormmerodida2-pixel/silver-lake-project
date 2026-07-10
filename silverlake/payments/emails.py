from decouple import config
from django.conf import settings
from django.contrib.auth import get_user_model

from core.email_utils import send_branded_email

from .models import PaymentMethod

User = get_user_model()


def send_offline_payment_recorded_email(payment):
    """Sent the moment a driver confirms a cash or card payment - the customer didn't initiate
    this confirmation themselves, so this is their one independent check: if they never actually
    paid (or a different amount), this email is what tips them off to dispute it. Only cash gets
    a dispute link right now (see payments.views.token_dispute_payment) - card doesn't have an
    equivalent self-service flow yet. Swallowed silently on failure so a misconfigured SMTP
    server never blocks the payment from being confirmed."""
    booking = payment.booking
    if not booking.customer_email:
        return
    method_label = payment.get_method_display()
    context = {
        'first_name': booking.customer_name.split()[0],
        'amount': f'{payment.amount:,.2f}',
        'method_label': method_label,
        'driver_name': payment.recorded_by_driver.full_name if payment.recorded_by_driver else 'your driver',
        'booking_id': booking.pk,
        'balance_due': f'{booking.balance_due:,.2f}',
    }
    if payment.method == PaymentMethod.CASH:
        frontend_url = config('FRONTEND_URL', default='http://localhost:5173')
        context['dispute_url'] = f'{frontend_url}/dispute-payment/{booking.customer_token}/{payment.pk}'
    try:
        send_branded_email(
            subject=f'{method_label} payment recorded on your SilverLake booking #{booking.pk}',
            template_name='emails/offline_payment_recorded.html',
            context=context,
            recipient_list=[booking.customer_email],
        )
    except Exception:
        pass


def send_cash_payment_staff_notification_email(payment):
    """Notifies every active staff account the moment a driver confirms a cash payment. Unlike
    M-Pesa (a receipt number lands immediately) or card, cash leaves no independent record
    anywhere until someone at SilverLake actually collects it from the driver - staff need their
    own heads-up to keep track of it, not just find out later while reconciling payouts. Cash
    only: M-Pesa and card already leave their own trail via a gateway."""
    staff_emails = list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )
    if not staff_emails:
        return

    booking = payment.booking
    send_branded_email(
        subject=f'Cash payment recorded — SilverLake booking #{booking.pk}',
        template_name='emails/cash_payment_staff_notification.html',
        context={
            'amount': f'{payment.amount:,.2f}',
            'customer_name': booking.customer_name,
            'driver_name': payment.recorded_by_driver.full_name if payment.recorded_by_driver else 'Unknown driver',
            'booking_id': booking.pk,
            'balance_due': f'{booking.balance_due:,.2f}',
            'payments_url': f'{settings.FRONTEND_URL}/admin/payments',
        },
        # Real staff addresses go in bcc so they don't see each other's emails; the To:
        # header just needs a placeholder so the message isn't sent with an empty To.
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
        bcc=staff_emails,
    )


def send_cash_deposit_reminder_email(payment):
    """Sent when staff nudge a driver who's confirmed collecting cash but hasn't yet redeposited
    it into the company Paybill (see payments.services.log_cash_deposit /
    PaymentViewSet.remind_deposit). Swallowed silently on failure so a misconfigured SMTP server
    never blocks the reminder from being recorded as sent."""
    driver = payment.recorded_by_driver
    booking = payment.booking
    if not driver or not driver.email:
        return
    try:
        send_branded_email(
            subject=f'Reminder: deposit cash to Paybill — SilverLake booking #{booking.pk}',
            template_name='emails/cash_deposit_reminder.html',
            context={
                'first_name': driver.full_name.split()[0],
                'amount': f'{payment.amount:,.2f}',
                'customer_name': booking.customer_name,
                'booking_id': booking.pk,
                'driver_portal_url': f'{settings.FRONTEND_URL}/driver',
            },
            recipient_list=[driver.email],
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
    """Sent when a payout is marked paid - the recipient's one confirmation/receipt that the
    money actually went out, beyond checking their own account. The recipient is either the
    individual driver-partner who owns the vehicle, or the FleetPartner organization that does
    (see payments.models.DriverPayout) - whichever it is, this is their notification. No-ops if
    they have no email on file; swallowed silently on failure so a misconfigured SMTP server
    never blocks the payout from being marked paid."""
    if payout.driver_id:
        recipient_name, recipient_email = payout.driver.full_name, payout.driver.email
    else:
        recipient_name, recipient_email = payout.organization.name, payout.organization.contact_email
    if not recipient_email:
        return
    booking = payout.booking
    try:
        send_branded_email(
            subject=f'Your payout has been paid — SilverLake booking #{booking.pk}',
            template_name='emails/payout_paid.html',
            context={
                'first_name': recipient_name.split()[0],
                'amount': f'{payout.amount:,.2f}',
                'booking_id': booking.pk,
                'customer_name': booking.customer_name,
                'reference': payout.payout_reference,
            },
            recipient_list=[recipient_email],
        )
    except Exception:
        pass


def send_payment_reminder_email(payment):
    """Sent when staff nudge a driver about a payment they declared (or a client declared on
    their behalf) but haven't yet confirmed receiving - see PaymentViewSet.remind. Swallowed
    silently on failure so a misconfigured SMTP server never blocks the reminder from being
    recorded as sent."""
    driver = payment.recorded_by_driver
    booking = payment.booking
    if not driver or not driver.email:
        return
    method_label = payment.get_method_display()
    try:
        send_branded_email(
            subject=f'Reminder: confirm a {method_label} payment — SilverLake booking #{booking.pk}',
            template_name='emails/payment_reminder.html',
            context={
                'first_name': driver.full_name.split()[0],
                'amount': f'{payment.amount:,.2f}',
                'method_label': method_label,
                'customer_name': booking.customer_name,
                'booking_id': booking.pk,
                'driver_portal_url': f'{settings.FRONTEND_URL}/driver',
            },
            recipient_list=[driver.email],
        )
    except Exception:
        pass


def send_offline_payment_driver_confirmation_email(payment):
    """Confirms to the driver themselves that their confirmed cash/card payment went through,
    and (for cash) sets expectations that it needs admin verification before their payout is
    released. Swallowed silently on failure so a misconfigured SMTP server never blocks the
    payment from being confirmed."""
    driver = payment.recorded_by_driver
    booking = payment.booking
    if not driver or not driver.email:
        return
    method_label = payment.get_method_display()
    try:
        send_branded_email(
            subject=f'{method_label} payment recorded — SilverLake booking #{booking.pk}',
            template_name='emails/offline_payment_driver_confirmation.html',
            context={
                'first_name': driver.full_name.split()[0],
                'amount': f'{payment.amount:,.2f}',
                'method_label': method_label,
                'customer_name': booking.customer_name,
                'booking_id': booking.pk,
                'balance_due': f'{booking.balance_due:,.2f}',
            },
            recipient_list=[driver.email],
        )
    except Exception:
        pass
