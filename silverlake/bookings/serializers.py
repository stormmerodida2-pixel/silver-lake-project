from copy import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from fleet.models import Vehicle
from payments.models import PaymentMethod, PaymentStatus
from reviews.serializers import ReviewSerializer

from .models import Booking, ServiceType

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
    needs_attention = serializers.BooleanField(read_only=True)
    vehicle_name = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    pending_payments = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'vehicle', 'vehicle_name', 'driver', 'driver_name', 'service_type', 'source',
            'customer_name', 'customer_phone', 'customer_email',
            'pickup_location', 'dropoff_location', 'start_date', 'end_date',
            'customer_license_number', 'customer_license_document', 'customer_id_document',
            'total_amount', 'amount_paid', 'balance_due', 'deposit_amount', 'is_deposit_paid',
            'status', 'notes', 'review', 'created_at', 'driver_acknowledged_at',
            'trip_started_at', 'trip_ended_at', 'needs_attention', 'pending_payments',
            'last_balance_reminder_at',
        ]
        read_only_fields = [
            'status', 'source', 'total_amount', 'created_at', 'driver_acknowledged_at',
            'trip_started_at', 'trip_ended_at', 'last_balance_reminder_at',
        ]

    def get_vehicle_name(self, obj):
        return obj.vehicle.name if obj.vehicle else '—'

    def get_driver_name(self, obj):
        return obj.driver.full_name if obj.driver else None

    def get_review(self, obj):
        review = getattr(obj, 'review', None)
        return ReviewSerializer(review).data if review else None

    def get_pending_payments(self, obj):
        # Cash/card payments the client has declared but the driver hasn't yet confirmed
        # actually receiving (see payments.services.declare_offline_payment) - surfaced so the
        # Driver Portal can prompt for confirmation, with the amount already locked in.
        payments = obj.payments.filter(
            method__in=(PaymentMethod.CASH, PaymentMethod.CARD), status=PaymentStatus.PENDING,
        )
        return [
            {'id': p.id, 'method': p.method, 'amount': p.amount, 'created_at': p.created_at}
            for p in payments
        ]


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


class DriverOnsiteBookingSerializer(serializers.Serializer):
    """A driver creating a booking on the spot for a walk-up client who won't be registering
    or logging in themselves. Always with_driver (it's the driver's own vehicle, in person),
    so none of the self-drive document fields apply."""

    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    customer_name = serializers.CharField(max_length=100)
    customer_phone = serializers.CharField(max_length=20)
    customer_email = serializers.EmailField(required=False, allow_blank=True, default='')
    pickup_location = serializers.CharField(max_length=200)
    dropoff_location = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_vehicle(self, vehicle):
        driver = self.context['driver']
        if vehicle.driver_id != driver.id:
            raise serializers.ValidationError("You can only book one of your own vehicles.")
        return vehicle

    def validate(self, attrs):
        driver = self.context['driver']
        candidate = Booking(
            vehicle=attrs['vehicle'], driver=driver, service_type=ServiceType.WITH_DRIVER,
            start_date=attrs['start_date'], end_date=attrs['end_date'],
        )
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return attrs
