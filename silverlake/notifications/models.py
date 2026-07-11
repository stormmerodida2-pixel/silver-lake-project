from django.conf import settings
from django.db import models


class NotificationEvent(models.TextChoices):
    DRIVER_ACKNOWLEDGED = 'driver_acknowledged', 'Driver Acknowledged Booking'
    BOOKING_CREATED = 'booking_created', 'New Booking'
    BOOKING_CANCELLED = 'booking_cancelled', 'Booking Cancelled'
    CASH_PAYMENT_RECORDED = 'cash_payment_recorded', 'Cash Payment Recorded'
    PAYMENT_DISPUTED = 'payment_disputed', 'Payment Disputed'
    DISPUTE_RESOLVED = 'dispute_resolved', 'Dispute Resolved'
    DRIVER_AWAY = 'driver_away', 'Driver Marked Away'
    VEHICLE_SUBMISSION = 'vehicle_submission', 'New Vehicle Submission'
    DRIVER_APPLICATION = 'driver_application', 'New Driver Application'


class Notification(models.Model):
    """An in-app event feed for the admin dashboard - the one notification channel that isn't
    email (see core.email_utils.send_branded_email for the email side, which most of these
    events already trigger alongside this). Org-scoped the same way as every other admin
    resource (see core.permissions.get_user_organization): organization=None means a genuine
    SilverLake platform event (invisible to an org-scoped account, same as Fleet Partners or the
    Activity Log), not "visible to everyone.\""""

    event = models.CharField(max_length=30, choices=NotificationEvent.choices)
    message = models.CharField(max_length=255)
    # Frontend admin route to open when clicked (e.g. '/admin/bookings') - a plain string is
    # enough since every event already has one obvious page to deep-link to; a full
    # contenttypes GenericForeignKey would be overkill just to know which page to open.
    link_path = models.CharField(max_length=200, blank=True)
    organization = models.ForeignKey(
        'fleet.FleetPartner', null=True, blank=True, on_delete=models.CASCADE, related_name='notifications',
    )
    # Who has seen it - same pattern as Announcement.read_by (presence only, no per-user
    # timestamped read-receipt log).
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='read_notifications')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_event_display()}: {self.message}'
