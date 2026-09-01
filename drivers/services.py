from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Driver

User = get_user_model()


def create_driver_login(driver):
    """Creates the User account backing a driver's portal login (if one doesn't already
    exist) and emails them a set-password invite. Safe to call again for a driver who
    already has an account - it just re-sends the invite/reset link.
    Skips silently if the driver has no email on file - nothing to invite."""
    if not driver.email:
        return

    if driver.user_id:
        user = driver.user
    else:
        first_name, _, last_name = driver.full_name.partition(' ')
        user, created = User.objects.get_or_create(
            username=driver.email,
            defaults={
                'email': driver.email,
                'first_name': first_name,
                'last_name': last_name,
                'is_active': True,
            },
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=['password'])

        driver.user = user
        driver.save(update_fields=['user'])

    from .emails import send_driver_portal_invite_email

    send_driver_portal_invite_email(user)


# How many days ahead of license expiry to send the advance warning - same value as, and same
# reasoning as, fleet.services.EXPIRY_WARNING_DAYS: long enough that the driver has a real
# chance to renew before their vehicle(s) silently drop out of visible_vehicles() (see
# fleet.models.visible_vehicles).
EXPIRY_WARNING_DAYS = 14


def warn_expiring_driver_licenses():
    """Runs on every scheduler tick (see payments.scheduler). A driver's license expiry is
    already enforced - visible_vehicles() silently drops any vehicle whose driver's license has
    lapsed - but until this, nothing ever told the driver (or staff) before or after it
    happened: their vehicle(s) could vanish from the public site with zero warning.

    Two independent checks, same shape as fleet.services.warn_expiring_vehicle_documents:
    - EXPIRY_WARNING_DAYS before the date, an advance-warning email/notification, so there's
      real time to renew before the vehicle(s) go dark.
    - The moment the date actually lapses, a same-day "this has now happened" email/
      notification - a missed or ignored warning still deserves a second, more urgent nudge
      once the vehicle(s) are actually hidden.

    Each check is guarded by its own `*_for` DateField holding the expiry date it was last sent
    for (see Driver's own fields), not a boolean or a cooldown timestamp - so renewing the
    license (which changes license_expiry_date to a new value) automatically makes the driver
    eligible for a fresh warning again next tick, with no separate reset step needed."""
    from notifications.models import NotificationEvent
    from notifications.services import notify

    from .emails import send_driver_license_expired_email, send_driver_license_expiring_email

    today = timezone.localdate()
    warning_cutoff = today + timedelta(days=EXPIRY_WARNING_DAYS)

    candidates = Driver.objects.filter(license_expiry_date__isnull=False)

    for driver in candidates:
        expiry_date = driver.license_expiry_date

        if expiry_date < today:
            if driver.license_expired_notified_for == expiry_date:
                continue
            driver.license_expired_notified_for = expiry_date
            driver.save(update_fields=['license_expired_notified_for'])
            send_driver_license_expired_email(driver, expiry_date)
            notify(
                NotificationEvent.DRIVER_LICENSE_EXPIRED,
                f"{driver.full_name}'s driving license has expired",
                link_path='/admin/drivers',
            )
            notify(
                NotificationEvent.DRIVER_LICENSE_EXPIRED,
                'Your driving license has expired and your vehicle(s) are now hidden from bookings',
                driver=driver, link_path='/driver',
            )
        elif expiry_date <= warning_cutoff:
            if driver.license_expiry_warned_for == expiry_date:
                continue
            driver.license_expiry_warned_for = expiry_date
            driver.save(update_fields=['license_expiry_warned_for'])
            days_remaining = (expiry_date - today).days
            send_driver_license_expiring_email(driver, expiry_date, days_remaining)
            notify(
                NotificationEvent.DRIVER_LICENSE_EXPIRING,
                f"{driver.full_name}'s driving license expires in {days_remaining} day(s)",
                link_path='/admin/drivers',
            )
            notify(
                NotificationEvent.DRIVER_LICENSE_EXPIRING,
                f'Your driving license expires in {days_remaining} day(s)',
                driver=driver, link_path='/driver',
            )
