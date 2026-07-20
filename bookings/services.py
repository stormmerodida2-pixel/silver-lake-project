from datetime import timedelta
from urllib.parse import quote

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    BLOCKING_BOOKING_STATUSES,
    Booking,
    BookingStatus,
    ConditionReportType,
    FuelLevel,
    VehicleConditionPhoto,
    VehicleConditionReport,
    WaitlistEntry,
)

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


def notify_waitlist_for_freed_dates(vehicle, start_date, end_date):
    """Called right after a booking is cancelled (see Booking.mark_cancelled) - tells anyone
    waitlisted for a date range that overlapped it, but only once that range genuinely has no
    remaining overlap with any other blocking booking on this vehicle (a second booking could
    still cover part of the same range). One-shot per entry (notified_at), even if it later gets
    re-blocked by a different booking - re-notifying on every subsequent cancellation would be
    noisy for no benefit, since the first notification already told them to act fast."""
    candidates = WaitlistEntry.objects.filter(
        vehicle=vehicle, notified_at__isnull=True, start_date__lte=end_date, end_date__gte=start_date,
    ).select_related('user')

    for entry in candidates:
        still_blocked = Booking.objects.filter(
            vehicle=vehicle, status__in=BLOCKING_BOOKING_STATUSES,
            start_date__lte=entry.end_date, end_date__gte=entry.start_date,
        ).exists()
        if still_blocked:
            continue

        entry.notified_at = timezone.now()
        entry.save(update_fields=['notified_at'])

        from .emails import send_waitlist_vehicle_available_email

        send_waitlist_vehicle_available_email(entry)


def create_condition_report(booking, report_type, mileage_raw, fuel_level, notes, photos, logged_by=None):
    """Shared by the driver-portal and admin creation endpoints (see bookings.views.
    DriverConditionReportCreateView / core.views.AdminBookingViewSet.condition_reports) - one
    report per type per booking (see VehicleConditionReport's own unique constraint), so a
    second attempt at the same type raises rather than silently overwriting the first. Raises
    django.core.exceptions.ValidationError on any bad input - callers translate that into a
    clean 400, matching how Booking.clean()/change_dates() are handled elsewhere in this app."""
    if report_type not in ConditionReportType.values:
        raise ValidationError(f'report_type must be one of: {", ".join(ConditionReportType.values)}.')
    if VehicleConditionReport.objects.filter(booking=booking, report_type=report_type).exists():
        raise ValidationError(
            f'A {ConditionReportType(report_type).label.lower()} condition report already exists for this booking.'
        )
    if fuel_level and fuel_level not in FuelLevel.values:
        raise ValidationError(f'fuel_level must be one of: {", ".join(FuelLevel.values)}.')

    mileage = None
    if mileage_raw not in (None, ''):
        try:
            mileage = int(mileage_raw)
        except (TypeError, ValueError):
            raise ValidationError('mileage must be a whole number.')

    report = VehicleConditionReport.objects.create(
        booking=booking, report_type=report_type, mileage=mileage,
        fuel_level=fuel_level, notes=notes or '', logged_by=logged_by,
    )
    for image in photos:
        VehicleConditionPhoto.objects.create(report=report, image=image)
    return report
