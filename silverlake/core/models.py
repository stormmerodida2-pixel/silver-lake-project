from django.conf import settings
from django.db import models


class StaffOrganization(models.Model):
    """Which FleetPartner a staff/admin account is scoped to - a genuine SilverLake platform
    account (staff or superadmin) simply has no row here, giving it unrestricted access exactly
    like before this model existed. Only ever created for `is_staff=True` accounts; a plain
    customer never has one. Kept as its own one-to-one (matching accounts.CustomerProfile's
    pattern) rather than a field on Django's built-in User, which this project doesn't
    subclass/replace. See core.permissions.get_user_organization for the safe lookup helper -
    don't access `user.staff_organization` directly, it raises when absent."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_organization')
    organization = models.ForeignKey('fleet.FleetPartner', on_delete=models.CASCADE, related_name='staff_accounts')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.email} @ {self.organization.name}'


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
