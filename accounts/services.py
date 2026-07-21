import random
import secrets
import string
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import CustomerProfile, LoginOTP, LoyaltyTier, ReferralCredit, ReferralSettings

User = get_user_model()

# How long a login OTP stays valid, and how many wrong guesses it tolerates before it's dead -
# long enough that a real email delivery delay doesn't lock someone out, short enough (combined
# with MAX_OTP_ATTEMPTS) that a 6-digit code (1M combinations) is never remotely brute-forceable
# within its own lifetime.
OTP_LIFETIME = timedelta(minutes=10)
MAX_OTP_ATTEMPTS = 5


def generate_otp_code():
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def request_login_otp(user):
    """Issues a fresh login OTP and emails it - called once a staff account with 2FA enabled has
    already passed the password check (see accounts.views.EmailTokenObtainPairSerializer.
    validate). Doesn't invalidate any earlier still-pending code for this user; verify_login_otp
    only ever looks at the most recent one, so an old code simply becomes unreachable rather than
    needing to be explicitly revoked."""
    otp = LoginOTP.objects.create(user=user, code=generate_otp_code())
    from .emails import send_login_otp_email
    send_login_otp_email(user, otp.code)
    return otp


def verify_login_otp(user, submitted_code):
    """Raises ValueError with a message safe to show the user for anything that fails - no code
    requested yet/expired, too many wrong guesses already, or a wrong code this time. Uses
    secrets.compare_digest rather than == so comparing the code doesn't leak timing information
    about how many leading digits matched."""
    cutoff = timezone.now() - OTP_LIFETIME
    otp = LoginOTP.objects.filter(user=user, is_used=False, created_at__gte=cutoff).order_by('-created_at').first()
    if not otp:
        raise ValueError('That code has expired. Please log in again to get a new one.')
    if otp.attempts >= MAX_OTP_ATTEMPTS:
        raise ValueError('Too many incorrect attempts. Please log in again to get a new code.')

    otp.attempts += 1
    if not secrets.compare_digest(otp.code, (submitted_code or '').strip()):
        otp.save(update_fields=['attempts'])
        raise ValueError('Incorrect code.')

    otp.is_used = True
    otp.save(update_fields=['is_used', 'attempts'])


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


def generate_referral_code():
    """An 8-character uppercase alphanumeric code - short enough to type or drop in a WhatsApp
    message, long enough that guessing someone else's isn't practical. Collisions are possible
    but vanishingly rare at this length; re-rolled on the rare hit rather than risking one."""
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(alphabet, k=8))
        if not CustomerProfile.objects.filter(referral_code=code).exists():
            return code


def award_referral_credit(referred_user):
    """Credits the referrer once their referred friend's first booking is actually confirmed
    (deposit paid) - not just registered, so a fake signup that never books can't farm credit.
    Idempotent per (referrer, referred_user) pair - called again on the referred user's second,
    third, etc. booking (see Booking.confirm_if_deposit_met) but only ever awards once. Uses
    whatever ReferralSettings.get_amount() is *right now* - an admin changing it later never
    retroactively changes a credit already awarded."""
    profile = getattr(referred_user, 'customer_profile', None)
    if not profile or not profile.referred_by_id:
        return None
    if ReferralCredit.objects.filter(user_id=profile.referred_by_id, referred_user=referred_user).exists():
        return None

    amount = ReferralSettings.get_amount()
    credit = ReferralCredit.objects.create(
        user_id=profile.referred_by_id, amount=amount, referred_user=referred_user,
    )

    from notifications.models import NotificationEvent
    from notifications.services import notify
    notify(
        NotificationEvent.REFERRAL_CREDIT_EARNED,
        f'You earned KES {amount:,.0f} in referral credit - '
        f'{referred_user.first_name or "your friend"} just booked their first trip!',
        user=profile.referred_by, link_path='/account/profile',
    )

    from .emails import send_referral_credit_earned_email
    send_referral_credit_earned_email(profile.referred_by, referred_user, amount)

    return credit


def get_available_credit_balance(user):
    """Sum of this user's own unredeemed referral credits - what's actually available to apply
    toward a future booking right now."""
    return ReferralCredit.objects.filter(user=user, redeemed_booking__isnull=True).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')


def get_redeemable_amount(user, max_amount):
    """Sum of this user's own oldest unredeemed credits that cumulatively fit within max_amount,
    stopping at the first one that would exceed it. Credits aren't all necessarily the same size
    - the admin-configurable amount (ReferralSettings) can change over time, so two credits on
    the same account may differ - this walks them oldest-first rather than assuming a uniform
    size, and never partially spends a single credit to hit an exact amount."""
    total = Decimal('0')
    credits = ReferralCredit.objects.filter(user=user, redeemed_booking__isnull=True).order_by('created_at')
    for credit in credits:
        if total + credit.amount > max_amount:
            break
        total += credit.amount
    return total


def get_completed_trip_count(user):
    """Lifetime completed trips - the loyalty program's own qualifying metric (see LoyaltyTier),
    deliberately narrower than the "genuine booking" definition used elsewhere (e.g.
    Booking._award_referral_credit_if_first_booking, AdminAnalyticsView's new-vs-repeat split,
    both of which count CONFIRMED-or-later): a trip that's merely confirmed or in progress hasn't
    actually happened for the customer yet, so it shouldn't count toward "how many trips you've
    taken with us"."""
    from bookings.models import Booking, BookingStatus

    return Booking.objects.filter(user=user, status=BookingStatus.COMPLETED).count()


def get_loyalty_tier(user):
    """The highest LoyaltyTier this user's own completed-trip count currently qualifies for, or
    None if even the lowest configured tier's threshold hasn't been met yet (e.g. no tiers
    exist, or the lowest one requires more trips than this customer has taken)."""
    trip_count = get_completed_trip_count(user)
    return LoyaltyTier.objects.filter(min_completed_trips__lte=trip_count).order_by('-min_completed_trips').first()


def get_next_loyalty_tier(user):
    """The next tier up from wherever this customer is now - for a "3 more trips to Gold"
    progress display. None means they've already reached the top configured tier (or none
    exist)."""
    trip_count = get_completed_trip_count(user)
    return LoyaltyTier.objects.filter(min_completed_trips__gt=trip_count).order_by('min_completed_trips').first()


def consume_referral_credit(user, amount, booking):
    """Marks unredeemed credits (oldest first) as spent against this booking, up to `amount` -
    the caller (payments.services.redeem_referral_credit) always derives `amount` from
    get_redeemable_amount first, so it's guaranteed to exactly match a prefix of the customer's
    own oldest credits and never requires splitting one."""
    remaining = amount
    credits = ReferralCredit.objects.filter(user=user, redeemed_booking__isnull=True).order_by('created_at')
    for credit in credits:
        if remaining <= 0:
            break
        credit.redeemed_booking = booking
        credit.redeemed_at = timezone.now()
        credit.save(update_fields=['redeemed_booking', 'redeemed_at'])
        remaining -= credit.amount
