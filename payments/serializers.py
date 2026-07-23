from decimal import Decimal

from rest_framework import serializers

from bookings.models import Booking

from .models import CashDeposit, Payment, PaymentMethod, PaymentStatus

# A declared bank transfer must come with at least this many characters of transaction
# reference - not validated against the strict 10-character M-Pesa format a cash deposit's
# reference is (see payments.services.MPESA_REFERENCE_PATTERN), since this could be a genuine
# inter-bank transfer with its own reference format, not necessarily M-Pesa-generated. Just
# enough that staff have something to actually search the real statement for. Shared with
# payments.views.token_declare_bank_transfer_payment (a plain function view, not this
# serializer), so it's defined once here rather than duplicated.
MIN_BANK_TRANSFER_REFERENCE_LENGTH = 4


class CashDepositSerializer(serializers.ModelSerializer):
    logged_by_name = serializers.CharField(source='logged_by.full_name', read_only=True, default=None)

    class Meta:
        model = CashDeposit
        fields = ['id', 'amount', 'mpesa_reference', 'logged_by_name', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    recorded_by_driver_name = serializers.SerializerMethodField()
    cash_deposit = CashDepositSerializer(read_only=True)
    reference_reused = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'booking', 'method', 'amount', 'status',
            'mpesa_receipt_number', 'phone_number', 'card_transaction_ref',
            'recorded_by_driver_name', 'note', 'reference_reused', 'is_disputed', 'disputed_at', 'dispute_note',
            'dispute_resolution_note', 'dispute_resolved_at',
            'cash_deposit', 'last_reminded_at', 'created_at',
        ]
        read_only_fields = [
            'status', 'mpesa_receipt_number', 'last_reminded_at', 'created_at',
            'dispute_resolution_note', 'dispute_resolved_at',
        ]

    def get_recorded_by_driver_name(self, obj):
        return obj.recorded_by_driver.full_name if obj.recorded_by_driver_id else None

    def get_reference_reused(self, obj):
        # A soft, staff-facing flag only - never a hard rejection at declare time. A short
        # reference (as little as the last 4 digits/characters, see
        # MIN_BANK_TRANSFER_REFERENCE_LENGTH) genuinely can recur by coincidence across two real,
        # unrelated transactions months apart, so blocking a declaration on a match would
        # eventually reject a legitimate payment. Surfacing it to staff instead lets a human weigh
        # it against the context an automated check can't see (does the amount/date/customer on
        # the real bank statement actually line up, or is this just a coincidental collision).
        if obj.method != PaymentMethod.BANK_TRANSFER or not obj.note:
            return False
        return Payment.objects.filter(method=PaymentMethod.BANK_TRANSFER, note=obj.note).exclude(pk=obj.pk).exists()


class StkPushRequestSerializer(serializers.Serializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())
    phone_number = serializers.CharField(help_text='M-Pesa number in 2547XXXXXXXX format')
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


class RedeemCreditRequestSerializer(serializers.Serializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())


class DeclareBankTransferRequestSerializer(serializers.Serializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    reference = serializers.CharField(
        min_length=MIN_BANK_TRANSFER_REFERENCE_LENGTH, max_length=100, trim_whitespace=True,
        help_text='Transaction reference - at minimum the last 4 digits/characters.',
    )


class TokenStkPushRequestSerializer(serializers.Serializer):
    """Same as StkPushRequestSerializer but without `booking` - the booking is already
    resolved from the URL's customer_token, so there's nothing to look up or trust from the body."""
    phone_number = serializers.CharField(help_text='M-Pesa number in 2547XXXXXXXX format')
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


class PublicBookingPaymentSerializer(serializers.ModelSerializer):
    """What a walk-up client sees on their no-login payment page - just enough to understand
    and pay for their trip, nothing else about their account or other bookings."""
    vehicle_name = serializers.CharField(source='vehicle.name', read_only=True)
    driver_name = serializers.SerializerMethodField()
    driver_cash_enabled = serializers.SerializerMethodField()
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    deposit_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_deposit_paid = serializers.BooleanField(read_only=True)
    pending_payments = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'vehicle_name', 'driver_name', 'driver_cash_enabled', 'customer_name', 'start_date', 'end_date',
            'total_amount', 'amount_paid', 'balance_due', 'deposit_amount', 'is_deposit_paid', 'status',
            'source', 'pending_payments',
        ]

    def get_driver_name(self, obj):
        return obj.driver.full_name if obj.driver else None

    def get_driver_cash_enabled(self, obj):
        return obj.driver.cash_payments_enabled if obj.driver else True

    def get_pending_payments(self, obj):
        # A cash/card/bank-transfer payment the client has already declared but nobody (driver,
        # for cash/card; staff, for bank transfer) has yet confirmed receiving - shown so the
        # client sees "declared, awaiting confirmation" rather than being able to declare the
        # same payment twice.
        payments = obj.payments.filter(
            method__in=(PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER),
            status=PaymentStatus.PENDING,
        )
        return [
            {'id': p.id, 'method': p.method, 'amount': p.amount, 'note': p.note, 'created_at': p.created_at}
            for p in payments
        ]
