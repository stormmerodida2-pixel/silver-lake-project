from django.contrib.auth import get_user_model

from accounts.emails import send_password_reset_email

from .models import StaffOrganization

User = get_user_model()


def invite_staff_account(email, organization=None, is_superuser=False, first_name='', last_name=''):
    """Creates (or upgrades an existing account into) a staff account and emails them a "set
    your password" link to actually access it - reuses the same token flow as a regular password
    reset rather than emailing a raw password, since a plaintext password sitting in an inbox
    indefinitely is easy to intercept and there's no reason to invent a separate mechanism when
    this one already exists (see accounts.emails.send_password_reset_email).

    `organization=None` means a genuine SilverLake platform staff account; passing a FleetPartner
    scopes the new account to just that organization instead (see core.models.StaffOrganization).
    If an account with this email already exists (e.g. a customer who's since being promoted to
    staff), it's upgraded in place rather than erroring - no reason someone can't be both."""
    user, created = User.objects.get_or_create(
        username__iexact=email,
        defaults={
            'username': email, 'email': email,
            'first_name': first_name, 'last_name': last_name,
            'is_staff': True, 'is_superuser': is_superuser, 'is_active': True,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
    else:
        user.is_staff = True
        user.is_superuser = user.is_superuser or is_superuser
        user.is_active = True
        user.save(update_fields=['is_staff', 'is_superuser', 'is_active'])

    if organization is not None:
        StaffOrganization.objects.update_or_create(user=user, defaults={'organization': organization})

    send_password_reset_email(user)
    return user
