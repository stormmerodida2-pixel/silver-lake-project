from django.conf import settings
from django.db import models

from .validators import validate_kenyan_phone_number


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
    # Best-effort owning FleetPartner, inferred from the target at write time (see
    # core.audit._infer_organization) - there's no single FK on the target itself in every case
    # (a Booking/Payment/Refund/DriverPayout each reach it their own way), so this is computed
    # once and stored rather than re-derived on every read. Null means either a genuine
    # platform-only action (driver suspension, an announcement, fleet-type taxonomy) or one
    # whose target has no derivable owning organization - same visibility every entry had
    # before this field existed, i.e. visible only to a real SilverLake staff/superadmin, never
    # to any org-scoped account. SET_NULL, not PROTECT, to match `actor` above: deleting a
    # FleetPartner should never be blocked by its own historical audit trail.
    organization = models.ForeignKey(
        'fleet.FleetPartner', null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_log_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        who = self.actor.email if self.actor_id else 'unknown'
        return f'{who} - {self.action} - {self.target_repr}'


class ClientErrorReport(models.Model):
    """Two distinct origins, one shared admin-visible log, so System Health's error table is
    "any error worth a superadmin's attention", not just the user-facing half:
    - CLIENT: a frontend JS crash, reported by frontend/src/utils/clientErrorReporting.js via
      core.views.ReportClientErrorView (this also covers a backend 500 as experienced by a real
      visitor's failed API call - see api/client.js's response interceptor).
    - SCHEDULER: a background sweep failure (payments.scheduler._sweep_loop) that happens with
      no HTTP request or user involved at all - previously only ever visible via `docker logs`,
      genuinely invisible anywhere in the admin UI otherwise.
    user is null both for a visitor who wasn't logged in and for every scheduler-sourced report
    (there's no request, so no one to attribute it to) - still worth keeping either way."""

    class Source(models.TextChoices):
        CLIENT = 'client', 'Client'
        SCHEDULER = 'scheduler', 'Background Job'

    source = models.CharField(max_length=20, choices=Source.choices, default=Source.CLIENT)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    message = models.CharField(max_length=500)
    stack = models.TextField(blank=True)
    url = models.CharField(max_length=500, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        who = self.user.email if self.user_id else 'anonymous visitor'
        return f'{who} - {self.message[:80]}'


class CorporateAccount(models.Model):
    """A company - a private business, or a government department - registered as a recurring
    billing entity, so an admin can create a booking "for" it (an employee's trip) with the
    balance settled later via invoice rather than the customer paying a deposit upfront. Admin-
    created only - no employee self-service login/booking, no credit_limit, no monthly invoice
    batching (see Booking.corporate_account / confirm_corporate_account /
    core.views.AdminBookingViewSet.create_corporate). Unbounded credit: nothing here ever blocks
    a booking from proceeding regardless of how large the unpaid balance grows - see
    Booking.bills_via_invoice.

    Platform-wide, not scoped to a FleetPartner - any staff can bill a trip to any registered
    company, regardless of whose vehicle is being booked."""

    name = models.CharField(max_length=150)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True, validators=[validate_kenyan_phone_number])
    # Lets a superadmin retire a company without deleting it and losing its booking/invoice
    # history - mirrors FleetPartner.is_active.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
