import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from pywebpush import WebPushException, webpush

from .models import PushSubscription

logger = logging.getLogger(__name__)
User = get_user_model()


def _recipients_for(notification):
    """Resolves a Notification's organization/driver/user scoping (see its own docstring - only
    ever one of the three is meaningfully set) down to the actual account(s) whose push
    subscriptions should receive it. Mirrors exactly what each of the three
    NotificationViewSet.get_queryset methods already computes for the in-app bell - the same
    row is "for" the same people either way, push is just a second way of reaching them."""
    if notification.user_id:
        return User.objects.filter(pk=notification.user_id)
    if notification.driver_id:
        return User.objects.filter(driver_profile=notification.driver_id)
    if notification.organization_id:
        # Platform staff sees every organization's own notifications too (see
        # NotificationViewSet.get_queryset), so both groups get the push.
        return User.objects.filter(is_staff=True, is_active=True).filter(
            Q(staff_organization__isnull=True) | Q(staff_organization__organization_id=notification.organization_id)
        )
    # organization explicitly None - a platform-wide admin event, genuine SilverLake staff only.
    return User.objects.filter(is_staff=True, is_active=True, staff_organization__isnull=True)


def send_push_notifications_for(notification):
    """Called right after a Notification is created (see notifications.services.notify) - a
    silent no-op until VAPID_PRIVATE_KEY is actually configured (see settings/base.py), same
    "blank env var disables it" shape as every other optional integration in this app. Respects
    the same per-user, per-event mute preference the in-app bell already does (NotificationPreference)
    - a muted event stays muted everywhere, not just in the bell it happens to be muted from."""
    if not settings.VAPID_PRIVATE_KEY:
        return
    recipients = _recipients_for(notification).exclude(muted_notification_events__event=notification.event)
    for subscription in PushSubscription.objects.filter(user__in=recipients):
        _send_one(subscription, notification)


def _send_one(subscription, notification):
    payload = json.dumps({
        'title': 'SilverLake Car Rentals',
        'body': notification.message,
        'url': notification.link_path or '/',
    })
    try:
        webpush(
            subscription_info={
                'endpoint': subscription.endpoint,
                'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
            },
            data=payload,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={'sub': f'mailto:{settings.VAPID_CLAIM_EMAIL}'},
        )
    except WebPushException as exc:
        # 404/410 mean the browser itself has permanently killed this subscription (site
        # uninstalled, permission revoked, profile deleted) - the push service is telling us to
        # stop trying, not a transient failure worth logging or retrying.
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in (404, 410):
            subscription.delete()
        else:
            logger.warning('Push notification to subscription %s failed: %s', subscription.pk, exc)
    except Exception:
        # Never let a push failure break the event it's riding along with (same rule as the
        # email/SMS sends every event already wraps in its own try/except).
        logger.exception('Unexpected error sending push notification %s', notification.pk)
