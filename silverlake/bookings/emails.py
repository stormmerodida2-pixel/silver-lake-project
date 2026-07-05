from core.email_utils import send_branded_email


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

