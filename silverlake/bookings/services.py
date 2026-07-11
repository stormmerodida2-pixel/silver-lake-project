from django.utils import timezone

from .models import Booking, BookingStatus


def escalate_unacknowledged_bookings():
    """Alerts staff, once per booking, when an online booking's assigned driver hasn't
    acknowledged it within its deadline (see Booking.acknowledgment_deadline) - a customer who
    booked a driver has no way to know whether that driver has actually seen it otherwise.
    Called from payments.scheduler's background sweep, same as
    payments.services.escalate_stuck_bookings - not payment-related, but reuses the same
    in-process scheduler this project already has rather than needing a second one.

    Deliberately does nothing automatic beyond notifying staff (no auto-reassignment) - a human
    decides whether to call the driver directly, reassign the booking to someone else, or wait
    a bit longer. Guarded by Booking.ack_escalated_at so the same booking is never escalated
    twice."""
    from notifications.models import NotificationEvent
    from notifications.services import notify

    from .emails import send_acknowledgment_overdue_staff_notification_email

    candidates = Booking.objects.filter(
        driver__isnull=False,
        driver_acknowledged_at__isnull=True,
        trip_started_at__isnull=True,
        ack_escalated_at__isnull=True,
    ).exclude(status__in=(BookingStatus.CANCELLED, BookingStatus.COMPLETED)).select_related('driver', 'vehicle')

    for booking in candidates:
        if not booking.is_acknowledgment_overdue:
            continue

        send_acknowledgment_overdue_staff_notification_email(booking)
        booking.ack_escalated_at = timezone.now()
        booking.save(update_fields=['ack_escalated_at'])
        notify(
            NotificationEvent.ACKNOWLEDGMENT_OVERDUE,
            f'Driver has not acknowledged booking #{booking.pk} within the deadline',
            organization=booking.vehicle.owner, link_path='/admin/bookings',
        )
