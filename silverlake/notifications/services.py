from .models import Notification


def notify(event, message, organization=None, driver=None, user=None, link_path=''):
    """Creates an in-app Notification - called alongside (never instead of) the existing email
    for events that already send one, plus a couple that previously had no notification at all
    (see silverlake/notifications/ callers). organization=None means a platform-wide admin event,
    invisible to an org-scoped account; driver targets a specific driver's own portal; user
    targets a specific client's own account - see Notification's own docstring."""
    return Notification.objects.create(
        event=event, message=message, organization=organization, driver=driver, user=user, link_path=link_path,
    )
