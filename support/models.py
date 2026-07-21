from django.conf import settings
from django.db import models

from bookings.validators import validate_file_size
from core.images import optimize_image


class TicketCategory(models.TextChoices):
    BILLING = 'billing', 'Billing Question'
    DAMAGE_DISPUTE = 'damage_dispute', 'Damage / Condition Dispute'
    BOOKING_ISSUE = 'booking_issue', 'Booking Issue'
    OTHER = 'other', 'Other'


class TicketStatus(models.TextChoices):
    OPEN = 'open', 'Open'
    IN_PROGRESS = 'in_progress', 'In Progress'
    RESOLVED = 'resolved', 'Resolved'


class SupportTicket(models.Model):
    """A customer-raised issue - a billing question, a dispute over a damage charge (see
    bookings.VehicleConditionReport, the evidence a dispute like that actually gets checked
    against), or anything else - filed from their own account, not the existing no-login
    cash-payment-dispute link (payments.views.token_dispute_payment), which is narrowly scoped
    to disputing one specific cash payment.

    Single-resolution-note model, not a full message thread: the customer describes the issue
    once, staff investigate and post one note that resolves it. A customer unsatisfied with the
    resolution can reopen it (see reopen()) rather than starting a second, unrelated ticket -
    reopening keeps the old resolution_note as-is (overwritten only by the *next* resolution),
    so a repeatedly-reopened ticket only ever shows its most recent outcome, not a full history.

    Platform-staff-only visibility (see core.permissions.IsPlatformStaff) - customer support is a
    SilverLake-wide function, not something delegated per FleetPartner, and a general question
    with no booking attached has no owning organization to scope it to anyway."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='support_tickets')
    # Optional - a billing question or general complaint may not be about any specific trip.
    booking = models.ForeignKey(
        'bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='support_tickets',
    )
    category = models.CharField(max_length=20, choices=TicketCategory.choices, default=TicketCategory.OTHER)
    subject = models.CharField(max_length=150)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=TicketStatus.choices, default=TicketStatus.OPEN)

    resolution_note = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk} {self.subject} ({self.get_status_display()})'

    def reopen(self):
        """Lets the customer who filed it reopen a resolved ticket they're not satisfied with -
        the previous resolution_note is left in place (only overwritten the next time staff
        resolve it again), so nothing about what was already said is lost."""
        self.status = TicketStatus.OPEN
        self.save(update_fields=['status', 'updated_at'])


class SupportTicketPhoto(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='support/', validators=[validate_file_size])
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.image and not self.image._committed:
            optimize_image(self.image)
        super().save(*args, **kwargs)
