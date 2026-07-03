from rest_framework import serializers

from .models import Driver, DriverApplication


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = ['id', 'full_name', 'photo', 'years_of_experience', 'bio', 'rating']


class DriverApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverApplication
        fields = [
            'id', 'full_name', 'email', 'phone_number', 'years_of_experience', 'bio',
            'license_number', 'license_document',
            'vehicle_name', 'vehicle_category', 'passenger_capacity', 'price_per_day',
            'vehicle_photo', 'vehicle_logbook_document',
            'status', 'created_at',
        ]
        read_only_fields = ['status', 'created_at']
