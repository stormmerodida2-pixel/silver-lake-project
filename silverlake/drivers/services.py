from django.contrib.auth import get_user_model

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
