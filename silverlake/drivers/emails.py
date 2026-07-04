from django.conf import settings
from django.contrib.auth import get_user_model

from core.email_utils import send_branded_email

User = get_user_model()


def send_new_driver_application_notification(application):
    """Notifies every active staff account that a new driver-partner application needs review."""
    staff_emails = list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )
    if not staff_emails:
        return

    review_url = f'{settings.FRONTEND_URL}/admin/drivers'
    send_branded_email(
        subject=f'New driver application: {application.full_name}',
        template_name='emails/new_application_admin_notice.html',
        context={'application': application, 'review_url': review_url},
        # Real staff addresses go in bcc so they don't see each other's emails; the To:
        # header just needs a placeholder so the message isn't sent with an empty To.
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
        bcc=staff_emails,
    )
