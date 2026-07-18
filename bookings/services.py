from datetime import timedelta
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Booking, BookingStatus

# Long enough that a genuine customer arranging an M-Pesa retry, a Paybill payment, or an
# in-person cash handoff with their driver has ample time, short enough that a checkout nobody
# ever came back to doesn't block the vehicle from public visibility (fleet.models.
# visible_vehicles treats any PENDING booking as "this vehicle is taken", same as the
# double-booking guard in BookingViewSet.create) for more than a day.
STALE_PENDING_BOOKING_THRESHOLD = timedelta(hours=24)


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
            organization=booking.vehicle.owner,
            link_path=f'/admin/bookings?search={quote(booking.customer_name)}',
        )


def expire_stale_pending_bookings():
    """Auto-cancels a PENDING booking that's had zero payment activity for
    STALE_PENDING_BOOKING_THRESHOLD - see that constant's own docstring for why this matters.

    Only touches a booking with genuinely no payment activity at all, successful or still
    pending - a customer mid-arrangement (an M-Pesa prompt just sent, a cash handoff already
    declared and awaiting driver confirmation) is left alone regardless of how old the booking
    itself is; the existing STK-push/cash-confirmation flows are what resolve those. Uses
    Booking.mark_cancelled() itself, so this gets exactly the same customer email/notification,
    refund-if-somehow-already-paid handling, and payout voiding as a real cancellation - because
    that's exactly what this is, just customer-initiated by inaction rather than by clicking
    Cancel."""
    from payments.models import PaymentStatus

    cutoff = timezone.now() - STALE_PENDING_BOOKING_THRESHOLD
    candidates = Booking.objects.filter(status=BookingStatus.PENDING, created_at__lt=cutoff).exclude(
        payments__status__in=(PaymentStatus.SUCCESSFUL, PaymentStatus.PENDING),
    )

    count = 0
    for booking in candidates:
        try:
            booking.mark_cancelled()
            count += 1
        except ValidationError:
            pass
    return count
