from .models import AuditLog


def log_admin_action(request, action, target, detail=''):
    """Records who performed a sensitive admin action and on what. Never allowed to break the
    request it's called from - logging failure shouldn't block the actual action succeeding."""
    try:
        AuditLog.objects.create(
            actor=request.user if request.user.is_authenticated else None,
            action=action,
            target_repr=str(target),
            detail=detail,
        )
    except Exception:
        pass
