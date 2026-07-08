from django.contrib.auth import get_user_model
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import CustomerProfile

User = get_user_model()


def blacklist_all_tokens_for_user(user):
    """Revokes every refresh token issued to this user - called whenever their password changes
    (via change-password or the forgot-password reset link), so a stolen session doesn't just
    keep working right through the one action a customer would actually take if they suspected
    their account was compromised. Only stops a token being used to mint a *new* access token -
    an access token already issued stays valid until it naturally expires (see
    SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'], kept short specifically because of this)."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


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
