from rest_framework import serializers

from fleet.serializers import VehicleSerializer
from fleet.models import VehicleSubmission, VehicleSubmissionPhoto

from .models import Driver, DriverApplication


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = ['id', 'full_name', 'photo', 'years_of_experience', 'bio', 'rating']


class VehicleSubmissionPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleSubmissionPhoto
        fields = ['id', 'image', 'order']


class VehicleSubmissionSerializer(serializers.ModelSerializer):
    images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, min_length=2,
        help_text='At least 2 photos of the vehicle.',
    )
    photos = VehicleSubmissionPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = VehicleSubmission
        fields = [
            'id', 'name', 'category', 'tagline', 'description', 'passenger_capacity',
            'price_per_day', 'images', 'photos', 'logbook_document', 'status', 'review_notes', 'created_at',
        ]
        read_only_fields = ['status', 'review_notes', 'created_at']

    def create(self, validated_data):
        images = validated_data.pop('images')
        submission = VehicleSubmission.objects.create(**validated_data)
        VehicleSubmissionPhoto.objects.bulk_create([
            VehicleSubmissionPhoto(submission=submission, image=image, order=i)
            for i, image in enumerate(images)
        ])
        return submission


class DriverPortalSerializer(serializers.ModelSerializer):
    vehicles = VehicleSerializer(many=True, read_only=True)
    vehicle_submissions = VehicleSubmissionSerializer(many=True, read_only=True)

    class Meta:
        model = Driver
        fields = [
            'id', 'full_name', 'email', 'phone_number', 'photo', 'years_of_experience',
            'bio', 'rating', 'is_away', 'away_reason', 'vehicles', 'vehicle_submissions',
        ]
        read_only_fields = [
            'full_name', 'email', 'phone_number', 'photo', 'years_of_experience', 'bio', 'rating',
        ]


class DriverAwaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = ['is_away', 'away_reason']


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
