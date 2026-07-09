from django.conf import settings
from django.db import models


class AnnouncementAudience(models.TextChoices):
    STAFF = 'staff', 'Staff'
    DRIVERS = 'drivers', 'Drivers'
    CLIENTS = 'clients', 'Clients'


class Announcement(models.Model):
    """A one-way broadcast from a superadmin to one audience - staff, drivers, or clients.
    In-app only (no email), so it's a cheap, low-stakes way to get a message in front of a
    whole group without a real bulk-email send."""

    title = models.CharField(max_length=150)
    body = models.TextField()
    audience = models.CharField(max_length=10, choices=AnnouncementAudience.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    # Uncheck to stop showing an announcement without deleting it (and losing who's read it).
    is_active = models.BooleanField(default=True)
    # Who has seen it - just presence, not a timestamped read-receipt log.
    read_by = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='read_announcements')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.get_audience_display()})'
