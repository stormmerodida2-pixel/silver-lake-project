import random
import string
from decimal import Decimal

from django.conf import settings
from django.db import models


class DiscountType(models.TextChoices):
    FIXED = 'fixed', 'Fixed amount (KES)'
    PERCENT = 'percent', 'Percentage'


def generate_discount_code():
    """An unused, random 8-char uppercase alphanumeric code - mirrors
    accounts.services.generate_referral_code's re-roll-on-collision approach. Only used as a
    fallback when an admin leaves the code field blank; an admin typing their own memorable code
    (e.g. "WELCOME500") works just as well, since uniqueness is enforced by the field itself."""
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(alphabet, k=8))
        if not DiscountCode.objects.filter(code=code).exists():
            return code


class DiscountCode(models.Model):
    """An admin-generated code a customer can enter once at booking time to reduce that
    booking's total - a fixed KES amount off, or a percentage off. Single-use and platform-wide:
    the first booking to redeem it burns it for everyone (see discounts.services.reserve_code) -
    there's no per-customer restriction, matching a simple one-off promo rather than a
    personalized coupon.

    Applied directly to Booking.total_amount at creation (see Booking.save()), before the 30%
    deposit is calculated off the already-discounted total - so it also lowers the deposit, the
    balance due, and (since driver payout is itself a percentage of total_amount) the assigned
    driver's payout. That's a deliberate platform-wide promotion cost, not something carved out
    of SilverLake's own margin the way referral credit is (contrast with
    accounts.services.award_referral_credit, which is realized as a separate Payment instead of
    ever touching total_amount)."""

    code = models.CharField(max_length=20, unique=True, blank=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.FIXED)
    value = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='A KES amount for a fixed discount, or a 0-100 number for a percentage discount.',
    )
    # Lets an admin turn a code off (typo'd, promo ended) without deleting it and losing the
    # record of who used it, if anyone already has.
    is_active = models.BooleanField(default=True)

    is_redeemed = models.BooleanField(default=False)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    # The booking it was actually spent on - null until redeemed. SET_NULL (not CASCADE/PROTECT):
    # a booking's payment/refund history already has to survive the user who placed it being
    # suspended rather than deleted (see Booking.user's own PROTECT); a discount code redemption
    # record shouldn't be any stricter than that.
    redeemed_booking = models.ForeignKey(
        'bookings.Booking', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper() if self.code else generate_discount_code()
        super().save(*args, **kwargs)

    def compute_discount(self, total):
        """The actual KES amount this code takes off a given pre-discount total - never more
        than the total itself (a fixed-amount code bigger than the booking just zeroes it out,
        rather than pushing total_amount negative)."""
        if self.discount_type == DiscountType.PERCENT:
            raw = (total * self.value / Decimal('100')).quantize(Decimal('0.01'))
        else:
            raw = self.value
        return min(raw, total)
