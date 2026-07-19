from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsDriverUser(BasePermission):
    """The logged-in account is linked to an active Driver record (has portal access).

    A superadmin impersonating a driver (see core.views.AdminUserViewSet.impersonate) gets a
    read-only session - the access token carries a `read_only` claim, checked here via
    request.auth (the validated token, set by JWTAuthentication) rather than request.user, so
    it's enforced on every driver-portal endpoint uniformly without touching each one
    individually. They can see exactly what the driver sees, for support, but never acknowledge
    a booking, start/end a trip, or declare a payment as them - those stay meaningfully
    driver-confirmed."""

    def has_permission(self, request, view):
        driver = getattr(request.user, 'driver_profile', None) if request.user.is_authenticated else None
        if not (driver and driver.is_active):
            return False
        if request.method not in SAFE_METHODS and request.auth and request.auth.get('read_only'):
            self.message = 'This is a read-only support session - you can view the driver portal but not act as this driver.'
            return False
        return True
