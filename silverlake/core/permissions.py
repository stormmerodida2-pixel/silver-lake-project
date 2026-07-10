from rest_framework.permissions import BasePermission


def get_user_organization(user):
    """The FleetPartner a staff/admin account is scoped to, or None for a genuine SilverLake
    platform account (staff or superadmin) with unrestricted access - safe to call on any user,
    staff or not, authenticated or not. `is_staff`/`is_superuser` keep meaning exactly what they
    always have (day-to-day vs. destructive/financial tier); this only narrows *whose* data those
    tiers apply to. See core.models.StaffOrganization."""
    if not getattr(user, 'is_authenticated', False):
        return None
    return getattr(getattr(user, 'staff_organization', None), 'organization', None)


class IsSupportStaff(BasePermission):
    """Any staff account, SilverLake's own or a FleetPartner's own org staff. Use for day-to-day
    operational actions: viewing, moderating reviews/driver applications, changing booking
    status, suspending/activating accounts. Pair with queryset scoping (get_user_organization)
    wherever the data itself needs to stay within one organization - this only checks the tier,
    not whose records are visible."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsSuperAdmin(BasePermission):
    """Superuser tier - SilverLake's own superadmin (unrestricted) or a FleetPartner's own
    org-admin (same tier of action, but their access is narrowed to their own organization's data
    via queryset scoping, not by this check). Use for destructive actions (delete) and anything
    that moves money or changes fleet composition/pricing (payouts, creating/editing/deleting
    vehicles) - within whichever scope the requester actually has."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsPlatformStaff(BasePermission):
    """SilverLake's own staff only - not a FleetPartner's org staff, even though they're also
    `is_staff=True`. Use for anything a partner organization has no business touching at all:
    SilverLake's own driver-partner onboarding pipeline, shared cross-platform taxonomy."""

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_staff
            and get_user_organization(request.user) is None
        )


class IsPlatformSuperAdmin(BasePermission):
    """SilverLake's own superadmin only - not a FleetPartner's org-admin, even though they're
    also `is_superuser=True`. Use for anything that must never be delegated to a partner:
    registering/editing other FleetPartners, mutating shared platform-wide taxonomy."""

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_superuser
            and get_user_organization(request.user) is None
        )
