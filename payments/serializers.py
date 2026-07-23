from decimal import Decimal

from rest_framework import serializers

from bookings.models import Booking

from .models import CashDeposit, Payment, PaymentMethod, PaymentStatus


class CashDepositSerializer(serializers.ModelSerializer):
    logged_by_name = serializers.CharField(source='logged_by.full_name', read_only=True, default=None)

    class Meta:
        model = CashDeposit
        fields = ['id', 'amount', 'mpesa_reference', 'logged_by_name', 'created_at']


class PaymentSerializer(serializers.ModelSerializer):
    recorded_by_driver_name = serializers.SerializerMethodField()
    cash_deposit = CashDepositSerializer(read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'booking', 'method', 'amount', 'status',
            'mpesa_receipt_number', 'phone_number', 'card_transaction_ref',
            'recorded_by_driver_name', 'note', 'is_disputed', 'disputed_at', 'dispute_note',
            'dispute_resolution_note', 'dispute_resolved_at',
            'cash_deposit', 'last_reminded_at', 'created_at',
        ]
        read_only_fields = [
            'status', 'mpesa_receipt_number', 'last_reminded_at', 'created_at',
            'dispute_resolution_note', 'dispute_resolved_at',
        ]

    def get_recorded_by_driver_name(self, obj):
        return obj.recorded_by_driver.full_name if obj.recorded_by_driver_id else None


class StkPushRequestSerializer(serializers.Serializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())
    phone_number = serializers.CharField(help_text='M-Pesa number in 2547XXXXXXXX format')
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


class RedeemCreditRequestSerializer(serializers.Serializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())


class DeclareBankTransferRequestSerializer(serializers.Serializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


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
            {'id': p.id, 'method': p.method, 'amount': p.amount, 'created_at': p.created_at}
            for p in payments
        ]
