from core.email_utils import send_branded_email


def send_driver_booking_notification(booking):
    """Notifies the assigned driver that a customer has booked them, once the booking is confirmed
    (deposit paid) - not at raw creation, so drivers aren't pinged for bookings nobody's paid for yet.
    Called from Booking.confirm_if_deposit_met(). No-ops if the driver has no email on file."""
    driver = booking.driver
    if not driver or not driver.email:
        return

    from django.conf import settings
    complete_url = f'{settings.FRONTEND_URL}/driver/booking/{booking.driver_token}'

    send_branded_email(
        subject='You have a new booking - SilverLake Car Rentals',
        template_name='emails/driver_booking_notice.html',
        context={
            'driver_name': driver.full_name,
            'booking': booking,
            'vehicle_name': booking.vehicle.name,
            'complete_url': complete_url,
        },
        recipient_list=[driver.email],
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
                'review_url': f'{settings.FRONTEND_URL}/reviews',
            },
            recipient_list=[booking.customer_email] if booking.customer_email else [],
        )
    except Exception:
        pass

