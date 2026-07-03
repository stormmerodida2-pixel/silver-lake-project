from django.contrib.auth import get_user_model
from rest_framework import serializers

from drivers.models import Driver
from payments.models import DriverPayout

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
