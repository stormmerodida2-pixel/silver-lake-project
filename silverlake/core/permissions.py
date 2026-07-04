from rest_framework.permissions import BasePermission


class IsSupportStaff(BasePermission):
    """Any staff account. Use for day-to-day operational actions: viewing, moderating
    reviews/driver applications, changing booking status, suspending/activating accounts."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsSuperAdmin(BasePermission):
    """Superusers only. Use for destructive actions (delete) and anything that moves money
    or changes fleet composition/pricing (payouts, creating/editing/deleting vehicles)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)
