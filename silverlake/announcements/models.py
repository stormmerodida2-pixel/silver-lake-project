from django.conf import settings
from django.db import models


class AnnouncementAudience(models.TextChoices):
    STAFF = 'staff', 'Staff'
    DRIVERS = 'drivers', 'Drivers'
    CLIENTS = 'clients', 'Clients'


class AnnouncementStatus(models.TextChoices):
    # Superadmin-authored announcements skip review entirely - only support-staff proposals
    # (always audience=clients) start out pending.
    APPROVED = 'approved', 'Approved'
    PENDING = 'pending', 'Pending review'
    REJECTED = 'rejected', 'Rejected'


class Announcement(models.Model):
    """A one-way broadcast to one audience - staff, drivers, or clients. In-app only (no
    email), so it's a cheap, low-stakes way to get a message in front of a whole group without
    a real bulk-email send.

    A superadmin can broadcast to any audience directly. Support staff can only propose
    client-facing announcements, which stay invisible to clients (status=pending) until a
    superadmin approves them - staff can talk to day-to-day customers, but a superadmin has to
    sign off before it reaches everyone at once."""

    title = models.CharField(max_length=150)
    body = models.TextField()
    audience = models.CharField(max_length=10, choices=AnnouncementAudience.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    # Uncheck to stop showing an announcement without deleting it (and losing who's read it).
    # Independent of status: an approved announcement can still be deactivated later.
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=AnnouncementStatus.choices, default=AnnouncementStatus.APPROVED)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    review_note = models.CharField(max_length=255, blank=True, help_text='Optional reason, shown to the submitter if rejected.')
    # Who has seen it - just presence, not a timestamped read-receipt log.
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='read_announcements')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.get_audience_display()})'
