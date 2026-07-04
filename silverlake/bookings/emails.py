from core.email_utils import send_branded_email


def send_driver_booking_notification(booking):
    """Notifies the assigned driver that a customer has booked them, once the booking is confirmed
    (deposit paid) - not at raw creation, so drivers aren't pinged for bookings nobody's paid for yet.
    Called from Booking.confirm_if_deposit_met(). No-ops if the driver has no email on file."""
    driver = booking.driver
    if not driver or not driver.email:
        return

    send_branded_email(
        subject='You have a new booking - SilverLake Car Rentals',
        template_name='emails/driver_booking_notice.html',
        context={
            'driver_name': driver.full_name,
            'booking': booking,
            'vehicle_name': booking.vehicle.name,
        },
        recipient_list=[driver.email],
    )
