from decimal import Decimal

from django.conf import settings
from django.db import models

from core.images import optimize_image
from fleet.validators import validate_file_size


class CustomerProfile(models.Model):
    """Optional profile for a registered customer account, linked to Django's built-in User."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='customer_profile')
    phone_number = models.CharField(max_length=20, blank=True)
    id_number = models.CharField(max_length=30, blank=True, help_text='National ID or passport number')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, validators=[validate_file_size])
    # Auto-generated on first save (see save() below) - every account gets one, whether or not
    # they ever share it. null=True (not just blank=True) so multiple not-yet-generated rows
    # never collide against the unique constraint at the DB level - genuinely NULL should never
    # persist past a save() in practice, but existing rows added by the migration that
    # introduced this field are NULL until a data migration backfills them.
    referral_code = models.CharField(max_length=8, unique=True, blank=True, null=True)
    # Set once, at registration, from whichever code (if any) was entered - see
    # RegisterSerializer. Never changes after that; SET_NULL rather than CASCADE so the referrer
    # deleting their account doesn't retroactively erase who referred this customer.
    referred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def save(self, *args, **kwargs):
        if self.avatar and not self.avatar._committed:
            optimize_image(self.avatar, max_dimension=500)
        if not self.referral_code:
            # Local import - accounts.services imports CustomerProfile from this same module.
            from .services import generate_referral_code
            self.referral_code = generate_referral_code()
        super().save(*args, **kwargs)


class ReferralCredit(models.Model):
    """A KES credit earned by referring a new customer whose first booking actually got
    confirmed (deposit paid) - see accounts.services.award_referral_credit. Applied as a
    discount on the referrer's own future booking (payments.services.redeem_referral_credit),
    never cash, never withdrawable/transferable. redeemed_booking is null until spent - each
    credit is either fully unredeemed or fully redeemed against exactly one booking, never split
    across two."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='referral_credits')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    referred_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+',
    )
    redeemed_booking = models.ForeignKey(
        'bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} - KES {self.amount} referral credit'

    @property
    def is_redeemed(self):
        return self.redeemed_booking_id is not None


class ReferralSettings(models.Model):
    """Single global row (see get_amount()/set_amount()) controlling the KES amount a referrer
    earns - admin-configurable (core.views.AdminReferralSettingsView) so running a promo or
    dialling it back is never a code deploy. Changing it only affects credits awarded from that
    point on; existing ReferralCredit rows keep whatever amount they were created with."""

    credit_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('500'))
    updated_at = models.DateTimeField(auto_now=True)

    # Enforced at the DB level too (not just by always using pk=1) - a second row here would
    # silently make get_amount()/set_amount() ambiguous about which one is "the" setting.
    SINGLETON_ID = 1

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_ID
        super().save(*args, **kwargs)

    @classmethod
    def get_amount(cls):
        row, _ = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return row.credit_amount

    @classmethod
    def set_amount(cls, amount):
        row, _ = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        row.credit_amount = amount
        row.save(update_fields=['credit_amount'])
        return row


class LoyaltyTier(models.Model):
    """An admin-configurable rung on the loyalty ladder - a customer's tier is derived live from
    their own lifetime completed-trip count (see accounts.services.get_loyalty_tier), never
    stored on the user themselves, so raising/lowering a threshold here immediately reflects
    everyone's real tier rather than needing a backfill. A customer's tier is the highest one
    whose min_completed_trips they've met; its discount_percent is applied automatically to
    every new booking they make from then on (see bookings.models.Booking.save) - no code
    needed, unlike discounts.DiscountCode, and stacks with one if the customer also has one."""

    name = models.CharField(max_length=50, unique=True)
    min_completed_trips = models.PositiveIntegerField(
        unique=True, help_text='Lifetime completed trips required to reach this tier.',
    )
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0'),
        help_text='Automatic discount applied to every booking once a customer reaches this tier.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['min_completed_trips']

    def __str__(self):
        return f'{self.name} ({self.min_completed_trips}+ trips, {self.discount_percent}% off)'
