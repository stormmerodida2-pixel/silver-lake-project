from .models import AuditLog


def _infer_organization(target):
    """Best-effort owning FleetPartner for an audit log entry, purely from the shape of
    whatever got logged - no call site has to know or pass this explicitly, since the ~35
    call sites across the app log all sorts of different target types. Falls back to None
    (platform-only, the same visibility every entry had before this field existed) for
    targets with no derivable owning organization, e.g. Driver, DriverApplication,
    Announcement, VehicleCategory - resources that don't belong to any one partner's fleet."""
    from fleet.models import FleetPartner

    if target is None:
        return None
    if isinstance(target, FleetPartner):
        return target
    for attr in ('organization', 'owner'):
        value = getattr(target, attr, None)
        if isinstance(value, FleetPartner):
            return value
    vehicle = getattr(target, 'vehicle', None)
    if vehicle is not None:
        return vehicle.owner
    booking = getattr(target, 'booking', None)
    if booking is not None:
        return booking.vehicle.owner
    staff_organization = getattr(target, 'staff_organization', None)
    if staff_organization is not None:
        return staff_organization.organization
    return None


def log_admin_action(request, action, target, detail=''):
    """Records who performed a sensitive admin action and on what. Never allowed to break the
    request it's called from - logging failure shouldn't block the actual action succeeding."""
    try:
        AuditLog.objects.create(
            actor=request.user if request.user.is_authenticated else None,
            action=action,
            target_repr=str(target),
            detail=detail,
            organization=_infer_organization(target),
        )
    except Exception:
        pass
