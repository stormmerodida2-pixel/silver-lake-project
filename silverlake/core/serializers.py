from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import CustomerProfile
from drivers.models import Driver
from drivers.serializers import VehicleSubmissionPhotoSerializer
from fleet.models import Vehicle, VehicleSubmission
from payments.models import DriverPayout, Refund
from reviews.models import Review

from .models import AuditLog

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    phone_number = serializers.SerializerMethodField()
    bookings_count = serializers.IntegerField(source='bookings.count', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone_number',
            'is_active', 'is_staff', 'is_superuser', 'date_joined', 'bookings_count',
        ]
        read_only_fields = ['email', 'date_joined']

    def get_phone_number(self, user):
        profile = getattr(user, 'customer_profile', None)
        return profile.phone_number if profile else ''

    def validate(self, attrs):
        request = self.context.get('request')
        if request and self.instance and self.instance == request.user:
            if attrs.get('is_superuser') is False or attrs.get('is_staff') is False:
                raise serializers.ValidationError("You can't remove your own admin access.")
        return attrs

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        phone_number = self.initial_data.get('phone_number')
        if phone_number is not None:
            CustomerProfile.objects.update_or_create(
                user=instance, defaults={'phone_number': phone_number}
            )
        return instance


class AdminCreateUserSerializer(serializers.Serializer):
    """Used by admins to directly create a new customer account (active immediately)."""

    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_email(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError('An account with this email already exists.')
        return value

    def create(self, validated_data):
        first_name, _, last_name = validated_data['full_name'].partition(' ')
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            first_name=first_name,
            last_name=last_name,
            password=validated_data['password'],
            is_active=True,  # Admin-created accounts skip email verification
        )
        CustomerProfile.objects.create(
            user=user,
            phone_number=validated_data.get('phone_number', ''),
        )
        return user


class AdminDriverSerializer(serializers.ModelSerializer):
    has_portal_account = serializers.BooleanField(source='user_id', read_only=True)

    class Meta:
        model = Driver
        fields = [
            'id', 'full_name', 'photo', 'email', 'phone_number',
            'years_of_experience', 'bio', 'rating', 'is_active',
            'is_away', 'away_reason', 'suspension_reason', 'has_portal_account', 'created_at',
        ]
        read_only_fields = ['is_away', 'away_reason', 'suspension_reason', 'created_at']


class AdminVehicleSubmissionSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='driver.full_name', read_only=True)
    photos = VehicleSubmissionPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = VehicleSubmission
        fields = [
            'id', 'driver', 'driver_name', 'name', 'category', 'tagline', 'description',
            'passenger_capacity', 'price_per_day', 'photos', 'logbook_document',
            'status', 'review_notes', 'created_at',
        ]
        read_only_fields = ['driver', 'status', 'created_at']


class AdminDriverPayoutSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='driver.full_name', read_only=True)
    booking_id = serializers.IntegerField(source='booking.id', read_only=True)
    customer_name = serializers.CharField(source='booking.customer_name', read_only=True)
    # Payouts are only ever created once a booking is fully paid (see Booking._ensure_driver_payout),
    # but surfacing these anyway gives admin a direct way to double-check that before disbursing -
    # e.g. if a booking's payment status were ever adjusted after the payout was already queued.
    booking_total_amount = serializers.DecimalField(source='booking.total_amount', max_digits=10, decimal_places=2, read_only=True)
    booking_amount_paid = serializers.DecimalField(source='booking.amount_paid', max_digits=10, decimal_places=2, read_only=True)
    booking_balance_due = serializers.DecimalField(source='booking.balance_due', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = DriverPayout
        fields = [
            'id', 'driver', 'driver_name', 'booking_id', 'customer_name',
            'booking_total_amount', 'booking_amount_paid', 'booking_balance_due',
            'amount', 'is_paid', 'paid_at', 'payout_reference', 'notes',
            'needs_verification', 'is_verified', 'verified_at', 'created_at',
        ]
        read_only_fields = ['driver', 'amount', 'paid_at', 'needs_verification', 'is_verified', 'verified_at', 'created_at']


class AdminAuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'actor_email', 'action', 'target_repr', 'detail', 'created_at']

    def get_actor_email(self, obj):
        return obj.actor.email if obj.actor_id else None


class AdminRefundSerializer(serializers.ModelSerializer):
    booking_id = serializers.IntegerField(source='booking.id', read_only=True)
    customer_name = serializers.CharField(source='booking.customer_name', read_only=True)

    class Meta:
        model = Refund
        fields = [
            'id', 'booking_id', 'customer_name', 'amount', 'status',
            'reference', 'notes', 'issued_at', 'created_at',
        ]
        read_only_fields = ['amount', 'status', 'issued_at', 'created_at']


class AdminVehicleSerializer(serializers.ModelSerializer):
    is_insurance_expired = serializers.BooleanField(read_only=True)
    is_inspection_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'name', 'category', 'tagline', 'passenger_capacity',
            'price_per_day', 'description', 'image', 'is_available',
            'allow_self_drive', 'allow_with_driver',
            'insurance_provider', 'insurance_policy_number', 'insurance_expiry_date',
            'inspection_expiry_date',
            'is_insurance_expired', 'is_inspection_expired',
            'created_at',
        ]
        read_only_fields = ['created_at', 'is_insurance_expired', 'is_inspection_expired']


class AdminReviewSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()
    booking_id = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id', 'customer_name', 'rating', 'comment', 'driver_name', 'booking_id', 'is_approved', 'created_at']
        read_only_fields = ['created_at']

    def get_driver_name(self, obj):
        return obj.driver.full_name if obj.driver_id else None

    def get_booking_id(self, obj):
        return obj.booking_id
