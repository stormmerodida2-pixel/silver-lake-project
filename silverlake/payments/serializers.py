from rest_framework import serializers

from bookings.models import Booking

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'booking', 'method', 'amount', 'status',
            'mpesa_receipt_number', 'phone_number', 'card_transaction_ref', 'created_at',
        ]
        read_only_fields = ['status', 'mpesa_receipt_number', 'created_at']


class StkPushRequestSerializer(serializers.Serializer):
    booking = serializers.PrimaryKeyRelatedField(queryset=Booking.objects.all())
    phone_number = serializers.CharField(help_text='M-Pesa number in 2547XXXXXXXX format')
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
