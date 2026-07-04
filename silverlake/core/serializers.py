from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import CustomerProfile
from drivers.models import Driver
from fleet.models import Vehicle
from payments.models import DriverPayout
from reviews.models import Review

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    phone_number = serializers.SerializerMethodField()
    bookings_count = serializers.IntegerField(source='bookings.count', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone_number',
            'is_active', 'is_staff', 'date_joined', 'bookings_count',
        ]
        read_only_fields = ['email', 'is_staff', 'date_joined']

    def get_phone_number(self, user):
        profile = getattr(user, 'customer_profile', None)
        return profile.phone_number if profile else ''


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
    class Meta:
        model = Driver
        fields = [
            'id', 'full_name', 'photo', 'phone_number',
            'years_of_experience', 'bio', 'rating', 'is_active', 'created_at',
        ]
        read_only_fields = ['created_at']


class AdminDriverPayoutSerializer(serializers.ModelSerializer):
    driver_name = serializers.CharField(source='driver.full_name', read_only=True)
    booking_id = serializers.IntegerField(source='booking.id', read_only=True)
    customer_name = serializers.CharField(source='booking.customer_name', read_only=True)

    class Meta:
        model = DriverPayout
        fields = [
            'id', 'driver', 'driver_name', 'booking_id', 'customer_name',
            'amount', 'is_paid', 'paid_at', 'payout_reference', 'notes', 'created_at',
        ]
        read_only_fields = ['driver', 'amount', 'paid_at', 'created_at']


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
    class Meta:
        model = Review
        fields = ['id', 'customer_name', 'rating', 'comment', 'is_approved', 'created_at']
        read_only_fields = ['created_at']
