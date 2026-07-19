from django.contrib.auth import get_user_model
from django.utils import timezone

from core.email_utils import send_branded_email
from notifications.sms import send_sms

User = get_user_model()


def send_driver_booking_sms(booking):
    """SMS companion to send_driver_booking_notification() below - same trigger, same no-op/
    swallow-on-failure rules, just a different channel. SMS is genuinely more likely to actually
    reach a driver quickly than email, so this isn't redundant with it."""
    driver = booking.driver
    if not driver or not driver.phone_number:
        return
    try:
        send_sms(
            driver.phone_number,
            f'New SilverLake booking! {booking.customer_name} booked your {booking.vehicle.name} '
            f'for {booking.rental_days} day(s) from {booking.start_date.strftime("%d %b")}. '
            f'Open the driver app to acknowledge.',
        )
    except Exception:
        pass


def send_driver_booking_notification(booking):
    """Notifies the assigned driver the moment an online customer books them - not gated on
    payment, so the driver finds out as soon as it happens and can acknowledge it from their
    dashboard. Called from BookingViewSet.perform_create(); never called for a driver's own
    walk-up bookings (see DriverOnsiteBookingCreateView). No-ops if the driver has no email on
    file. Swallowed silently on failure so a misconfigured SMTP server never blocks the booking
    from being created."""
    driver = booking.driver
    if not driver or not driver.email:
        return

    try:
        from django.conf import settings
        portal_url = f'{settings.FRONTEND_URL}/driver'

        send_branded_email(
            subject='New booking - please review - SilverLake Car Rentals',
            template_name='emails/driver_booking_notice.html',
            context={
                'driver_name': driver.full_name,
                'booking': booking,
                'vehicle_name': booking.vehicle.name,
                'portal_url': portal_url,
            },
            recipient_list=[driver.email],
        )
    except Exception:
        pass


def send_booking_cancelled_email(booking):
    """Sent whenever a booking is cancelled, whether by the customer themselves or by staff -
    previously there was no notification at all, so a staff-initiated cancellation would leave
    the customer finding out only by checking 'My Bookings'. Swallowed silently on failure so a
    misconfigured SMTP server never blocks the cancellation."""
    if not booking.customer_email:
        return
    try:
        send_branded_email(
            subject=f'Your SilverLake booking #{booking.pk} has been cancelled',
            template_name='emails/booking_cancelled.html',
            context={
                'first_name': booking.customer_name.split()[0],
                'booking_id': booking.pk,
                'vehicle_name': booking.vehicle.name,
                'amount_paid': f'{booking.amount_paid:,.2f}' if booking.amount_paid > 0 else None,
            },
            recipient_list=[booking.customer_email],
        )
    except Exception:
        pass


def send_booking_balance_reminder_email(booking):
    """Nudges the assigned driver that this booking still has an outstanding balance - see
    core.views.AdminBookingViewSet.remind_balance. No-ops if the driver has no email on file. Swallowed
    silently on failure so a misconfigured SMTP server never blocks the reminder from being
    recorded as sent."""
    driver = booking.driver
    if not driver or not driver.email:
        return
    try:
        from django.conf import settings
        send_branded_email(
            subject=f'Reminder: outstanding balance on booking #{booking.pk}',
            template_name='emails/booking_balance_reminder.html',
            context={
                'driver_name': driver.full_name,
                'booking': booking,
                'customer_name': booking.customer_name,
                'balance_due': f'{booking.balance_due:,.2f}',
                'portal_url': f'{settings.FRONTEND_URL}/driver',
            },
            recipient_list=[driver.email],
        )
    except Exception:
        pass


def send_payment_escalation_staff_notification_email(booking, reasons):
    """Sent once per booking, by the automated reminder sweep (see
    payments.services.escalate_stuck_bookings), when a payment/deposit issue has sat unresolved
    for days despite the driver already being auto-reminded - staff need to step in and chase it
    directly rather than waiting for the driver to act on their own. `reasons` is a list of
    short human-readable strings (e.g. "a declared payment is still unconfirmed") describing
    what's actually still outstanding, since more than one can apply at once."""
    staff_emails = list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )
    if not staff_emails:
        return

    from django.conf import settings

    send_branded_email(
        subject=f'Needs attention: booking #{booking.pk} — unresolved payment for days',
        template_name='emails/payment_escalation_staff_notification.html',
        context={
            'booking_id': booking.pk,
            'customer_name': booking.customer_name,
            'driver_name': booking.driver.full_name if booking.driver_id else 'No driver assigned',
            'reasons': reasons,
            'bookings_url': f'{settings.FRONTEND_URL}/admin/bookings',
        },
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
        bcc=staff_emails,
    )


def send_acknowledgment_overdue_staff_notification_email(booking):
    """Sent once per booking, by the automated escalation sweep (see
    bookings.services.escalate_unacknowledged_bookings), when the assigned driver hasn't
    acknowledged an online booking within its deadline (see Booking.acknowledgment_deadline) -
    the customer is waiting to find out their driver has actually seen the booking, so staff
    need to step in and chase it directly (call the driver, or reassign) rather than the
    booking silently sitting unacknowledged until someone happens to notice."""
    staff_emails = list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )
    if not staff_emails:
        return

    from urllib.parse import quote

    from django.conf import settings

    send_branded_email(
        subject=f'Needs attention: driver hasn\'t acknowledged booking #{booking.pk}',
        template_name='emails/acknowledgment_overdue_staff_notification.html',
        context={
            'booking_id': booking.pk,
            'customer_name': booking.customer_name,
            'driver_name': booking.driver.full_name if booking.driver_id else 'No driver assigned',
            'deadline': timezone.localtime(booking.acknowledgment_deadline).strftime('%d %b %Y, %H:%M'),
            # Pre-filters the admin Bookings list to this exact booking, so staff land
            # straight on the row that needs a replacement driver instead of having to
            # search for it themselves - reassigning is just changing the driver dropdown
            # right there in the list, no separate edit screen needed.
            'bookings_url': f'{settings.FRONTEND_URL}/admin/bookings?search={quote(booking.customer_name)}',
        },
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
        bcc=staff_emails,
    )


def send_trip_completed_email(booking):
    """Sends a review request email to the customer on trip completion."""
    try:
        from django.conf import settings
        send_branded_email(
            subject=f'How was your ride with SilverLake? (Booking #{booking.pk})',
            template_name='emails/trip_completed.html',
            context={
                'first_name': booking.customer_name.split()[0],
                'vehicle_name': booking.vehicle.name,
                'review_url': f'{settings.FRONTEND_URL}/account/bookings',
            },
            recipient_list=[booking.customer_email] if booking.customer_email else [],
        )
    except Exception:
        pass


def send_waitlist_vehicle_available_email(entry):
    """Sent once (see bookings.services.notify_waitlist_for_freed_dates) when a vehicle a
    customer was waitlisted for opens up for their requested dates. Purely a heads-up - it's not
    a hold, so whoever actually books first still wins. No-ops if the account somehow has no
    email on file. Swallowed silently on failure so a misconfigured SMTP server never blocks the
    waitlist entry from being marked notified."""
    if not entry.user.email:
        return
    try:
        from django.conf import settings

        send_branded_email(
            subject=f'{entry.vehicle.name} is now available for your dates - SilverLake Car Rentals',
            template_name='emails/waitlist_vehicle_available.html',
            context={
                'first_name': entry.user.first_name.split()[0] if entry.user.first_name else 'there',
                'vehicle_name': entry.vehicle.name,
                'start_date': entry.start_date,
                'end_date': entry.end_date,
                'booking_url': f'{settings.FRONTEND_URL}/book?vehicle={entry.vehicle_id}',
            },
            recipient_list=[entry.user.email],
        )
    except Exception:
        pass

