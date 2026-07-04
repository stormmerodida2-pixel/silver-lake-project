from django.contrib.auth import get_user_model

from .models import CustomerProfile

User = get_user_model()


def get_or_create_customer_account(full_name, phone_number, email=''):
    """Finds or creates a lightweight customer account for someone who doesn't have one yet -
    used when a driver creates an on-site booking for a walk-up client who won't be registering
    themselves. Looks up by email if given, otherwise by phone number, so the same walk-up
    client re-uses one account across visits instead of getting a new one each time.

    The account has no usable password until the customer sets one (e.g. via a password-reset
    link, if they ever add an email and want to log in) - for a one-off payment they never need
    a password at all, since the token-based payment link doesn't require login.
    """
    username = email or f'phone:{phone_number}'
    user = User.objects.filter(username__iexact=username).first()
    if user:
        return user, False

    first_name, _, last_name = full_name.strip().partition(' ')
    user = User.objects.create_user(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_active=True,
    )
    user.set_unusable_password()
    user.save(update_fields=['password'])
    CustomerProfile.objects.create(user=user, phone_number=phone_number)
    return user, True
