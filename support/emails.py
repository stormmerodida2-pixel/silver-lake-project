from django.conf import settings
from django.contrib.auth import get_user_model

from core.email_utils import send_branded_email

User = get_user_model()


def send_support_ticket_created_staff_notification_email(ticket):
    """Notifies SilverLake's own platform staff (never a FleetPartner's org staff - see
    SupportTicket's own docstring for why support stays platform-wide) the moment a customer
    files a new ticket. Swallowed silently on failure so a misconfigured SMTP server never blocks
    the ticket itself from being filed."""
    staff_emails = list(
        User.objects.filter(
            is_staff=True, is_active=True, staff_organization__isnull=True,
        ).exclude(email='').values_list('email', flat=True)
    )
    if not staff_emails:
        return
    try:
        send_branded_email(
            subject=f'New support ticket — {ticket.subject}',
            template_name='emails/support_ticket_created_staff_notification.html',
            context={
                'ticket_id': ticket.pk,
                'customer_name': ticket.user.get_full_name() or ticket.user.email,
                'category': ticket.get_category_display(),
                'subject': ticket.subject,
                'description': ticket.description,
                'booking_id': ticket.booking_id,
                'support_url': f'{settings.FRONTEND_URL}/admin/support',
            },
            recipient_list=[settings.DEFAULT_FROM_EMAIL],
            bcc=staff_emails,
        )
    except Exception:
        pass


def send_support_ticket_resolved_email(ticket):
    """Sent when staff resolve a customer's ticket - their only signal otherwise would be
    checking back on the app themselves. Swallowed silently on failure so a misconfigured SMTP
    server never blocks the resolution from being recorded."""
    if not ticket.user.email:
        return
    try:
        send_branded_email(
            subject=f'Your support ticket has been resolved — {ticket.subject}',
            template_name='emails/support_ticket_resolved.html',
            context={
                'first_name': (ticket.user.first_name or ticket.user.email).split()[0],
                'ticket_id': ticket.pk,
                'subject': ticket.subject,
                'resolution_note': ticket.resolution_note,
                'support_url': f'{settings.FRONTEND_URL}/account/support',
            },
            recipient_list=[ticket.user.email],
        )
    except Exception:
        pass
