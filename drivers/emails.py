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


def _driver_license_staff_emails():
    return list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )


def send_driver_license_expiring_email(driver, expiry_date, days_remaining):
    """Sent EXPIRY_WARNING_DAYS before a driver's license lapses (see
    drivers.services.warn_expiring_driver_licenses) - real advance notice to renew before their
    vehicle(s) silently drop out of visible_vehicles() (see fleet.models.visible_vehicles).
    Addressed to the driver directly (a license is inherently personal, not tied to vehicle
    ownership the way insurance/inspection are), with staff bcc'd for visibility."""
    staff_emails = _driver_license_staff_emails()
    if not driver.email and not staff_emails:
        return

    context = {
        'first_name': driver.full_name.split()[0],
        'driver_name': driver.full_name,
        'expiry_date': expiry_date.strftime('%d %b %Y'),
        'days_remaining': days_remaining,
        'drivers_url': f'{settings.FRONTEND_URL}/admin/drivers',
    }
    subject = f'Driving license expiring soon — {driver.full_name}'
    if driver.email:
        send_branded_email(
            subject=subject, template_name='emails/driver_license_expiring.html', context=context,
            recipient_list=[driver.email], bcc=staff_emails,
        )
    else:
        send_branded_email(
            subject=subject, template_name='emails/driver_license_expiring.html', context=context,
            recipient_list=[settings.DEFAULT_FROM_EMAIL], bcc=staff_emails,
        )


def send_driver_license_expired_email(driver, expiry_date):
    """Sent the day a driver's license actually lapses - by this point visible_vehicles() has
    already silently pulled their vehicle(s) from public listings, so this is more urgent than
    the advance warning above."""
    staff_emails = _driver_license_staff_emails()
    if not driver.email and not staff_emails:
        return

    context = {
        'first_name': driver.full_name.split()[0],
        'driver_name': driver.full_name,
        'expiry_date': expiry_date.strftime('%d %b %Y'),
        'drivers_url': f'{settings.FRONTEND_URL}/admin/drivers',
    }
    subject = f'Driving license expired — {driver.full_name}'
    if driver.email:
        send_branded_email(
            subject=subject, template_name='emails/driver_license_expired.html', context=context,
            recipient_list=[driver.email], bcc=staff_emails,
        )
    else:
        send_branded_email(
            subject=subject, template_name='emails/driver_license_expired.html', context=context,
            recipient_list=[settings.DEFAULT_FROM_EMAIL], bcc=staff_emails,
        )


def send_driver_away_notification(driver):
    """Notifies every active staff account that a driver has marked themselves away - their
    vehicle(s) are hidden from the public fleet until they mark themselves available again."""
    staff_emails = list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )
    if not staff_emails:
        return

    review_url = f'{settings.FRONTEND_URL}/admin/drivers'
    send_branded_email(
        subject=f'Driver marked as away: {driver.full_name}',
        template_name='emails/driver_away_admin_notice.html',
        context={'driver': driver, 'review_url': review_url},
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
        bcc=staff_emails,
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


def send_driver_application_rejected_email(application):
    """Sent when an admin rejects a 'become a driver' application - approval already tells the
    applicant via the portal-invite email, but rejection previously left them never hearing
    back at all. Swallowed silently on failure so a misconfigured SMTP server never blocks the
    application from being processed."""
    try:
        send_branded_email(
            subject='Update on your SilverLake driver application',
            template_name='emails/driver_application_rejected.html',
            context={'first_name': application.full_name.split()[0], 'notes': application.review_notes},
            recipient_list=[application.email],
        )
    except Exception:
        pass


def send_vehicle_submission_approved_email(submission):
    """Sent when a driver-partner's own submitted vehicle is approved and goes live. No-ops if
    the driver has no email on file; swallowed silently on failure so a misconfigured SMTP
    server never blocks the submission from being approved."""
    driver = submission.driver
    if not driver.email:
        return
    try:
        send_branded_email(
            subject=f'Your {submission.name} is now live on SilverLake',
            template_name='emails/vehicle_submission_approved.html',
            context={
                'first_name': driver.full_name.split()[0],
                'vehicle_name': submission.name,
                'portal_url': f'{settings.FRONTEND_URL}/driver',
            },
            recipient_list=[driver.email],
        )
    except Exception:
        pass


def send_vehicle_submission_rejected_email(submission):
    """Sent when a driver-partner's own submitted vehicle is rejected - previously the driver
    had no way to find out except by checking their portal. No-ops if the driver has no email
    on file; swallowed silently on failure so a misconfigured SMTP server never blocks the
    submission from being processed."""
    driver = submission.driver
    if not driver.email:
        return
    try:
        send_branded_email(
            subject=f'Update on your {submission.name} submission',
            template_name='emails/vehicle_submission_rejected.html',
            context={
                'first_name': driver.full_name.split()[0],
                'vehicle_name': submission.name,
                'notes': submission.review_notes,
            },
            recipient_list=[driver.email],
        )
    except Exception:
        pass
