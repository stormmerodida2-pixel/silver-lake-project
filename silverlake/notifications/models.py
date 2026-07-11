from django.conf import settings
from django.db import models


class NotificationEvent(models.TextChoices):
    # Admin-facing (organization-scoped, see NotificationViewSet)
    DRIVER_ACKNOWLEDGED = 'driver_acknowledged', 'Driver Acknowledged Booking'
    BOOKING_CREATED = 'booking_created', 'New Booking'
    BOOKING_CANCELLED = 'booking_cancelled', 'Booking Cancelled'
    CASH_PAYMENT_RECORDED = 'cash_payment_recorded', 'Cash Payment Recorded'
    PAYMENT_DISPUTED = 'payment_disputed', 'Payment Disputed'
    DISPUTE_RESOLVED = 'dispute_resolved', 'Dispute Resolved'
    DRIVER_AWAY = 'driver_away', 'Driver Marked Away'
    VEHICLE_SUBMISSION = 'vehicle_submission', 'New Vehicle Submission'
    DRIVER_APPLICATION = 'driver_application', 'New Driver Application'
    # Driver-facing (see DriverNotificationViewSet) - BOOKING_CANCELLED above is reused for
    # these too, since a cancelled trip is relevant to both audiences at once.
    DRIVER_BOOKED = 'driver_booked', 'You Were Booked'
    PAYMENT_REMINDER = 'payment_reminder', 'Payment Reminder'
    CASH_DEPOSIT_REMINDER = 'cash_deposit_reminder', 'Cash Deposit Reminder'
    PAYOUT_PAID = 'payout_paid', 'Payout Paid'
    VEHICLE_SUBMISSION_APPROVED = 'vehicle_submission_approved', 'Vehicle Submission Approved'
    VEHICLE_SUBMISSION_REJECTED = 'vehicle_submission_rejected', 'Vehicle Submission Rejected'
    # Client-facing (see ClientNotificationViewSet) - BOOKING_CANCELLED above is reused here too.
    BOOKING_CONFIRMED = 'booking_confirmed', 'Booking Confirmed'
    TRIP_COMPLETED = 'trip_completed', 'Trip Completed'
    PAYMENT_RECORDED = 'payment_recorded', 'Payment Recorded'
    REFUND_ISSUED = 'refund_issued', 'Refund Issued'


class Notification(models.Model):
    """An in-app event feed for the admin dashboard, the driver portal, and a client's own
    account - the one notification channel that isn't email (see
    core.email_utils.send_branded_email for the email side, which most of these events already
    trigger alongside this).

    Exactly one of organization/driver/user is ever meaningfully set for a given event -
    organization for admin-dashboard events (scoped the same way as every other admin resource,
    see core.permissions.get_user_organization: organization=None means a genuine SilverLake
    platform event, invisible to an org-scoped account, same as Fleet Partners or the Activity
    Log, not "visible to everyone"), driver for driver-portal events (scoped to exactly that one
    driver's own portal - see DriverNotificationViewSet), user for a specific client's own
    account (see ClientNotificationViewSet) - a client has no separate profile model the way a
    driver does, so this targets the login account (Booking.user) directly."""

    event = models.CharField(max_length=30, choices=NotificationEvent.choices)
    message = models.CharField(max_length=255)
    # Frontend route to open when clicked (e.g. '/admin/bookings', '/driver', '/account/bookings')
    # - a plain string is enough since every event already has one obvious page to deep-link to;
    # a full contenttypes GenericForeignKey would be overkill just to know which page to open.
    link_path = models.CharField(max_length=200, blank=True)
    organization = models.ForeignKey(
        'fleet.FleetPartner', null=True, blank=True, on_delete=models.CASCADE, related_name='notifications',
    )
    driver = models.ForeignKey(
        'drivers.Driver', null=True, blank=True, on_delete=models.CASCADE, related_name='notifications',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name='client_notifications',
    )
    # Who has seen it - same pattern as Announcement.read_by (presence only, no per-user
    # timestamped read-receipt log).
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='read_notifications')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_event_display()}: {self.message}'
