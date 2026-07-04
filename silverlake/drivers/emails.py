from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.email_utils import send_branded_email

User = get_user_model()


def send_driver_portal_invite_email(user):
    """Sent when a driver's portal login is first created - reuses the password-reset flow
    so the driver picks their own password rather than us emailing one in plaintext."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f'{settings.FRONTEND_URL}/reset-password/{uid}/{token}'
    send_branded_email(
        subject='Your SilverLake Driver Portal account is ready',
        template_name='emails/driver_portal_invite.html',
        context={'first_name': user.first_name, 'set_password_url': link},
        recipient_list=[user.email],
    )


def send_driver_suspended_email(driver, reason):
    """Sent when an admin suspends a driver - lets them know why, since it also takes
    their vehicle(s) off the public fleet listing."""
    if not driver.email:
        return
    send_branded_email(
        subject='Your SilverLake driver account has been suspended',
        template_name='emails/driver_suspended.html',
        context={'first_name': driver.full_name.split()[0], 'reason': reason},
        recipient_list=[driver.email],
    )


def send_new_vehicle_submission_notification(submission):
    """Notifies every active staff account that a driver submitted a car for review."""
    staff_emails = list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )
    if not staff_emails:
        return

    review_url = f'{settings.FRONTEND_URL}/admin/drivers'
    send_branded_email(
        subject=f'New vehicle submitted for review: {submission.name}',
        template_name='emails/new_vehicle_submission_admin_notice.html',
        context={'submission': submission, 'review_url': review_url},
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
        bcc=staff_emails,
    )


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
