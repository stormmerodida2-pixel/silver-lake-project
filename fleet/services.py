"""Fleet-side background sweep helpers - see payments.scheduler for how these get wired into
the project's single in-process scheduler."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Vehicle

# How many days ahead of insurance/inspection expiry to send the advance warning - long enough
# that whoever's responsible (see Vehicle._document_responsible_party) has a real chance to
# renew before the vehicle silently drops out of visible_vehicles() (see
# fleet.models.visible_vehicles).
EXPIRY_WARNING_DAYS = 14

# (doc label, expiry-date field, "warned for this date" field, "notified-expired for this date" field)
_DOCUMENT_FIELDS = (
    ('Insurance', 'insurance_expiry_date', 'insurance_expiry_warned_for', 'insurance_expired_notified_for'),
    ('Inspection', 'inspection_expiry_date', 'inspection_expiry_warned_for', 'inspection_expired_notified_for'),
)


def warn_expiring_vehicle_documents():
    """Runs on every scheduler tick (see payments.scheduler). Insurance and inspection expiry
    are already enforced - visible_vehicles() silently drops any vehicle past either date - but
    until this, nothing ever told anyone before or after it happened: a vehicle could vanish
    from the public site with zero warning to whoever's responsible for renewing it, and zero
    heads-up to staff either.

    Two independent checks per document (insurance, inspection):
    - EXPIRY_WARNING_DAYS before the date, an advance-warning email/notification, so there's
      real time to renew before the vehicle goes dark.
    - The moment the date actually lapses, a same-day "this has now happened" email/
      notification - a missed or ignored warning still deserves a second, more urgent nudge
      once the vehicle is actually hidden.

    Each of the four checks is guarded by its own `*_for` DateField holding the expiry date it
    was last sent for (see Vehicle's own fields), not a boolean or a cooldown timestamp - so
    renewing the document (which changes the expiry date to a new value) automatically makes
    the vehicle eligible for a fresh warning again next tick, with no separate reset step
    needed."""
    from notifications.models import NotificationEvent

    from .emails import send_vehicle_document_expired_email, send_vehicle_document_expiring_email

    today = timezone.localdate()
    warning_cutoff = today + timedelta(days=EXPIRY_WARNING_DAYS)

    candidates = Vehicle.objects.filter(
        Q(insurance_expiry_date__isnull=False) | Q(inspection_expiry_date__isnull=False)
    ).select_related('owner', 'driver')

    for vehicle in candidates:
        for doc_label, date_field, warned_field, notified_field in _DOCUMENT_FIELDS:
            expiry_date = getattr(vehicle, date_field)
            if not expiry_date:
                continue

            if expiry_date < today:
                if getattr(vehicle, notified_field) == expiry_date:
                    continue
                setattr(vehicle, notified_field, expiry_date)
                vehicle.save(update_fields=[notified_field])
                send_vehicle_document_expired_email(vehicle, doc_label, expiry_date)
                _notify_vehicle_event(
                    vehicle, NotificationEvent.VEHICLE_DOCUMENT_EXPIRED,
                    f"{vehicle.name}'s {doc_label.lower()} has expired and it's now hidden from bookings",
                )
            elif expiry_date <= warning_cutoff:
                if getattr(vehicle, warned_field) == expiry_date:
                    continue
                setattr(vehicle, warned_field, expiry_date)
                vehicle.save(update_fields=[warned_field])
                days_remaining = (expiry_date - today).days
                send_vehicle_document_expiring_email(vehicle, doc_label, expiry_date, days_remaining)
                _notify_vehicle_event(
                    vehicle, NotificationEvent.VEHICLE_DOCUMENT_EXPIRING,
                    f"{vehicle.name}'s {doc_label.lower()} expires in {days_remaining} day(s)",
                )


def _notify_vehicle_event(vehicle, event, message):
    """Scopes the in-app Notification the same way the email is scoped (see
    Vehicle._document_responsible_party): a FleetPartner-owned vehicle's own org admins, an
    individually driver-owned vehicle's own driver portal, or platform-wide for a company-owned
    vehicle with nobody external to notify. Shared by both warn_expiring_vehicle_documents and
    warn_due_vehicle_service below - the ownership-based scoping is identical either way."""
    from notifications.services import notify

    _email, _name, driver = vehicle._document_responsible_party()
    if vehicle.owner_id:
        notify(event, message, organization=vehicle.owner, link_path='/admin/fleet')
    elif driver:
        notify(event, message, driver=driver, link_path='/driver/vehicles')
    else:
        notify(event, message, link_path='/admin/fleet')


def warn_due_vehicle_service():
    """Runs on every scheduler tick (see payments.scheduler). Vehicle.is_service_due is fully
    computed - 90 days since the last logged VehicleServiceRecord, or since the vehicle went
    live (see Vehicle.service_due_date) - and already surfaced as a badge on Admin Fleet, the
    driver portal, and a dashboard count, but until this, nothing ever proactively told anyone
    before or after a vehicle actually became due. Unlike insurance/inspection/license, an
    overdue service never hides the vehicle from bookings (see fleet.models.visible_vehicles,
    which never excludes on this) - it's purely informational, so this sweep is the only thing
    keeping it from being missed entirely.

    Same two-phase warn-before/alert-on-lapse shape as warn_expiring_vehicle_documents, with
    Vehicle.service_due_date standing in for an explicit expiry_date - self-healing the same
    way: logging a new VehicleServiceRecord shifts service_due_date forward, so the `*_for`
    fields below naturally stop matching and the vehicle becomes eligible for a fresh warning
    again, with no separate reset step needed."""
    from notifications.models import NotificationEvent

    from .emails import send_vehicle_service_due_soon_email, send_vehicle_service_overdue_email

    today = timezone.localdate()
    warning_cutoff = today + timedelta(days=EXPIRY_WARNING_DAYS)

    candidates = Vehicle.objects.select_related('owner', 'driver').prefetch_related('service_records')

    for vehicle in candidates:
        due_date = vehicle.service_due_date

        if due_date < today:
            if vehicle.service_overdue_notified_for == due_date:
                continue
            vehicle.service_overdue_notified_for = due_date
            vehicle.save(update_fields=['service_overdue_notified_for'])
            send_vehicle_service_overdue_email(vehicle, due_date)
            _notify_vehicle_event(
                vehicle, NotificationEvent.VEHICLE_SERVICE_OVERDUE,
                f'{vehicle.name} is now overdue for service',
            )
        elif due_date <= warning_cutoff:
            if vehicle.service_due_warned_for == due_date:
                continue
            vehicle.service_due_warned_for = due_date
            vehicle.save(update_fields=['service_due_warned_for'])
            days_remaining = (due_date - today).days
            send_vehicle_service_due_soon_email(vehicle, due_date, days_remaining)
            _notify_vehicle_event(
                vehicle, NotificationEvent.VEHICLE_SERVICE_DUE_SOON,
                f'{vehicle.name} is due for service in {days_remaining} day(s)',
            )
