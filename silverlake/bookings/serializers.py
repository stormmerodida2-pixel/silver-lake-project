from copy import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Booking

# Fields Booking.clean() actually looks at - kept in sync with the validation logic there.
CLEAN_RELEVANT_FIELDS = (
    'vehicle', 'driver', 'start_date', 'end_date', 'service_type',
    'customer_license_document', 'customer_id_document',
)


class BookingSerializer(serializers.ModelSerializer):
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    deposit_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    is_deposit_paid = serializers.BooleanField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'vehicle', 'driver', 'service_type',
            'customer_name', 'customer_phone', 'customer_email',
            'pickup_location', 'dropoff_location', 'start_date', 'end_date',
            'customer_license_number', 'customer_license_document', 'customer_id_document',
            'total_amount', 'amount_paid', 'balance_due', 'deposit_amount', 'is_deposit_paid',
            'status', 'notes', 'created_at',
        ]
        read_only_fields = ['status', 'total_amount', 'created_at']

    def validate(self, attrs):
        # Delegate to Booking.clean() so the same date-order/vehicle/driver-conflict/self-drive-
        # document rules apply here and in the Django admin (which calls clean() via its
        # ModelForm, but never runs this DRF serializer).
        if self.instance is not None:
            candidate = copy(self.instance)
            for field in CLEAN_RELEVANT_FIELDS:
                if field in attrs:
                    setattr(candidate, field, attrs[field])
        else:
            candidate = Booking(**{field: attrs.get(field) for field in CLEAN_RELEVANT_FIELDS})

        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)

        return attrs
