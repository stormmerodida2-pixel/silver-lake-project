from django.conf import settings
from django.contrib.auth import get_user_model

from core.email_utils import send_branded_email

User = get_user_model()


def _staff_emails():
    return list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )


def _send_document_email(vehicle, subject, template_name, extra_context):
    """Shared dispatch for both the advance-warning and lapsed emails below - addresses
    whoever's responsible for the vehicle (see Vehicle._document_responsible_party), always
    bcc'ing staff too, and falling back to a staff-only send (same recipient_list/bcc pattern
    every other staff-only notification here uses) when there's nobody external to address, or
    they have no email on file. No-ops entirely if there's truly nobody to reach."""
    recipient_email, recipient_name, _driver = vehicle._document_responsible_party()
    staff_emails = _staff_emails()
    if not recipient_email and not staff_emails:
        return

    context = {**extra_context, 'first_name': recipient_name.split()[0] if recipient_name else ''}
    if recipient_email:
        send_branded_email(
            subject=subject, template_name=template_name, context=context,
            recipient_list=[recipient_email], bcc=staff_emails,
        )
    else:
        send_branded_email(
            subject=subject, template_name=template_name, context=context,
            recipient_list=[settings.DEFAULT_FROM_EMAIL], bcc=staff_emails,
        )


def send_vehicle_document_expiring_email(vehicle, doc_label, expiry_date, days_remaining):
    """Sent EXPIRY_WARNING_DAYS before a vehicle's insurance/inspection lapses (see
    fleet.services.warn_expiring_vehicle_documents) - real advance notice to renew before the
    vehicle silently drops out of visible_vehicles() (see fleet.models.visible_vehicles)."""
    _send_document_email(
        vehicle,
        subject=f'{doc_label} expiring soon — {vehicle.name}',
        template_name='emails/vehicle_document_expiring.html',
        extra_context={
            'vehicle_name': vehicle.name,
            'doc_label': doc_label,
            'expiry_date': expiry_date.strftime('%d %b %Y'),
            'days_remaining': days_remaining,
            'fleet_url': f'{settings.FRONTEND_URL}/admin/fleet',
        },
    )


def send_vehicle_document_expired_email(vehicle, doc_label, expiry_date):
    """Sent the day a vehicle's insurance/inspection actually lapses - by this point
    visible_vehicles() has already silently pulled it from public listings, so this is more
    urgent than the advance warning above: the vehicle is losing bookings right now."""
    _send_document_email(
        vehicle,
        subject=f'{doc_label} expired — {vehicle.name} is now hidden from bookings',
        template_name='emails/vehicle_document_expired.html',
        extra_context={
            'vehicle_name': vehicle.name,
            'doc_label': doc_label,
            'expiry_date': expiry_date.strftime('%d %b %Y'),
            'fleet_url': f'{settings.FRONTEND_URL}/admin/fleet',
        },
    )
