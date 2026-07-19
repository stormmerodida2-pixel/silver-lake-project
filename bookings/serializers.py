from copy import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from discounts.models import DiscountCode
from discounts.services import DiscountCodeError, find_active_code, reserve_code
from drivers.models import Driver
from fleet.models import Vehicle
from payments.models import PaymentMethod, PaymentStatus
from reviews.serializers import ReviewSerializer

from .models import Booking, ServiceType, WaitlistEntry

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
    acknowledgment_deadline = serializers.DateTimeField(read_only=True)
    is_acknowledgment_overdue = serializers.BooleanField(read_only=True)
    vehicle_name = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    pending_payments = serializers.SerializerMethodField()
    pending_cash_deposits = serializers.SerializerMethodField()
    # Write-only: a customer optionally types a discount code (see discounts.DiscountCode) at
    # booking time - it's applied and consumed inside create() below, never exposed as the raw
    # FK. discount_code_display/discount_amount (both read-only) show what actually got applied.
    discount_code = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=20)
    discount_code_display = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'vehicle', 'vehicle_name', 'driver', 'driver_name', 'service_type', 'source',
            'customer_name', 'customer_phone', 'customer_email',
            'pickup_location', 'dropoff_location', 'start_date', 'end_date',
            'customer_license_number', 'customer_license_document', 'customer_id_document',
            'total_amount', 'amount_paid', 'balance_due', 'deposit_amount', 'is_deposit_paid',
            'discount_code', 'discount_code_display', 'discount_amount',
            'status', 'notes', 'review', 'created_at', 'driver_acknowledged_at',
            'trip_started_at', 'trip_ended_at', 'needs_attention', 'acknowledgment_deadline',
            'is_acknowledgment_overdue', 'pending_payments',
            'pending_cash_deposits', 'last_balance_reminder_at',
            'is_government_contract', 'government_contract_reference',
        ]
        read_only_fields = [
            'status', 'source', 'total_amount', 'discount_amount', 'created_at',
            'driver_acknowledged_at', 'trip_started_at', 'trip_ended_at',
            'last_balance_reminder_at', 'is_government_contract', 'government_contract_reference',
        ]

    def get_vehicle_name(self, obj):
        return obj.vehicle.name if obj.vehicle else '—'

    def get_driver_name(self, obj):
        return obj.driver.full_name if obj.driver else None

    def get_discount_code_display(self, obj):
        return obj.discount_code.code if obj.discount_code_id else None

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

    def get_pending_cash_deposits(self, obj):
        # Confirmed cash payments the assigned driver has collected but not yet deposited to the
        # company Paybill - surfaced so the Driver Portal can prompt for the deposit, and so a
        # payout can't quietly get verified while one of these is still outstanding.
        payments = obj.payments.filter(
            method=PaymentMethod.CASH, status=PaymentStatus.SUCCESSFUL, cash_deposit__isnull=True,
        )
        return [
            {'id': p.id, 'amount': p.amount, 'created_at': p.created_at}
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

        discount_code = attrs.get('discount_code')
        if discount_code:
            if self.instance is not None:
                # Only ever applied at creation, when total_amount is first computed (see
                # Booking.save()) - an existing booking's total can't retroactively pick up a
                # code applied after the fact through this same general-purpose update endpoint.
                raise serializers.ValidationError(
                    {'discount_code': 'A discount code can only be applied when creating a booking.'}
                )
            # A cheap, friendly pre-check - not itself a reservation (see find_active_code's own
            # docstring). The actual single-use guarantee happens atomically in create() below.
            try:
                find_active_code(discount_code)
            except DiscountCodeError as exc:
                raise serializers.ValidationError({'discount_code': str(exc)})

        return attrs

    def create(self, validated_data):
        discount_code_str = (validated_data.pop('discount_code', '') or '').strip()
        discount_code_obj = None
        if discount_code_str:
            try:
                discount_code_obj = reserve_code(discount_code_str)
            except DiscountCodeError as exc:
                raise serializers.ValidationError({'discount_code': str(exc)})

        booking = Booking(**validated_data)
        if discount_code_obj:
            booking.discount_code = discount_code_obj
        booking.save()

        if discount_code_obj:
            DiscountCode.objects.filter(pk=discount_code_obj.pk).update(
                redeemed_booking=booking, redeemed_at=timezone.now(),
            )

        return booking


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


class AdminGovernmentBookingSerializer(serializers.Serializer):
    """An admin creating a government-contract booking on behalf of a department that will
    never register or log in itself - mirrors DriverOnsiteBookingSerializer's plain-Serializer
    + Booking.clean() reuse, but with an explicit driver choice (an admin can assign any of the
    vehicle's eligible drivers, not just their own) and a required contract reference."""

    vehicle = serializers.PrimaryKeyRelatedField(queryset=Vehicle.objects.all())
    driver = serializers.PrimaryKeyRelatedField(queryset=Driver.objects.all(), required=False, allow_null=True)
    service_type = serializers.ChoiceField(choices=ServiceType.choices, default=ServiceType.WITH_DRIVER)
    customer_name = serializers.CharField(max_length=100)
    customer_phone = serializers.CharField(max_length=20)
    customer_email = serializers.EmailField(required=False, allow_blank=True, default='')
    pickup_location = serializers.CharField(max_length=200)
    dropoff_location = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    government_contract_reference = serializers.CharField(max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        candidate = Booking(
            vehicle=attrs['vehicle'], driver=attrs.get('driver'), service_type=attrs['service_type'],
            start_date=attrs['start_date'], end_date=attrs['end_date'],
        )
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return attrs


class WaitlistEntrySerializer(serializers.ModelSerializer):
    vehicle_name = serializers.CharField(source='vehicle.name', read_only=True)
    vehicle_image = serializers.SerializerMethodField()

    class Meta:
        model = WaitlistEntry
        fields = ['id', 'vehicle', 'vehicle_name', 'vehicle_image', 'start_date', 'end_date', 'notified_at', 'created_at']
        read_only_fields = ['id', 'vehicle_name', 'vehicle_image', 'notified_at', 'created_at']

    def get_vehicle_image(self, entry):
        if not entry.vehicle.image:
            return None
        request = self.context.get('request')
        url = entry.vehicle.image.url
        return request.build_absolute_uri(url) if request else url
