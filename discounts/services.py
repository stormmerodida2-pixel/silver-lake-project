from .models import DiscountCode


class DiscountCodeError(Exception):
    """Raised when a submitted discount code can't be redeemed - invalid, inactive, or already
    used. Caught at the API boundary (see bookings.serializers.BookingSerializer.create) and
    turned into a clean 400."""


def find_active_code(code_str):
    """Read-only lookup for a friendly, early error message (see
    bookings.serializers.BookingSerializer.validate) - not itself a safe reservation. The real
    single-use guarantee is reserve_code's atomic conditional update, run later inside the same
    transaction as the booking's own creation."""
    code = DiscountCode.objects.filter(code=code_str.strip().upper(), is_active=True, is_redeemed=False).first()
    if not code:
        raise DiscountCodeError('This discount code is invalid, inactive, or has already been used.')
    return code


def reserve_code(code_str):
    """Atomically claims a code for use, inside the caller's own transaction - the same
    "conditional UPDATE, check the row count" trick BookingViewSet.create already uses to
    prevent a double-booked vehicle: a second concurrent redemption of the same code loses this
    race and gets a clean error, since SQLite's select_for_update() is a documented no-op and
    can't be relied on here. Only reserves the code itself (is_redeemed=True) - the caller sets
    redeemed_booking/redeemed_at once the booking it's for actually has a pk."""
    updated = DiscountCode.objects.filter(
        code=code_str.strip().upper(), is_active=True, is_redeemed=False,
    ).update(is_redeemed=True)
    if not updated:
        raise DiscountCodeError('This discount code is invalid, inactive, or has already been used.')
    return DiscountCode.objects.get(code=code_str.strip().upper())
