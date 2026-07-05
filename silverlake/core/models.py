from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """A record of who did what for the admin actions that move money or change someone's
    access - suspending a driver, verifying/paying a payout, issuing a refund, editing a
    user's roles. Kept even if the actor's account is later deleted."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='audit_log_entries',
    )
    action = models.CharField(max_length=100)
    target_repr = models.CharField(max_length=255, blank=True)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        who = self.actor.email if self.actor_id else 'unknown'
        return f'{who} - {self.action} - {self.target_repr}'
