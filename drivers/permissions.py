from rest_framework.permissions import BasePermission


class IsDriverUser(BasePermission):
    """The logged-in account is linked to an active Driver record (has portal access)."""

    def has_permission(self, request, view):
        driver = getattr(request.user, 'driver_profile', None) if request.user.is_authenticated else None
        return bool(driver and driver.is_active)
