from rest_framework import serializers

from fleet.models import VehicleCategory, VehicleSubmission, VehicleSubmissionPhoto
from fleet.serializers import VehicleSerializer, VehicleServiceRecordSerializer

from .models import Driver, DriverApplication


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = ['id', 'full_name', 'photo', 'years_of_experience', 'bio', 'rating']


class DriverVehicleSerializer(VehicleSerializer):
    """The public VehicleSerializer plus service history - kept separate from the public one
    so service records (internal maintenance info) never leak into the public /api/vehicles/
    listing, only the driver's own portal view of their own vehicle."""

    service_records = VehicleServiceRecordSerializer(many=True, read_only=True)
    is_service_due = serializers.BooleanField(read_only=True)

    class Meta(VehicleSerializer.Meta):
        fields = VehicleSerializer.Meta.fields + ['service_records', 'is_service_due']


class VehicleSubmissionPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleSubmissionPhoto
        fields = ['id', 'image', 'order']


class VehicleSubmissionSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field='slug', queryset=VehicleCategory.objects.all())
    category_name = serializers.CharField(source='category.name', read_only=True)
    images = serializers.ListField(
        child=serializers.ImageField(), write_only=True, min_length=2,
        help_text='At least 2 photos of the vehicle.',
    )
    photos = VehicleSubmissionPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = VehicleSubmission
        fields = [
            'id', 'name', 'category', 'category_name', 'tagline', 'description', 'passenger_capacity',
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
    vehicles = DriverVehicleSerializer(many=True, read_only=True)
    vehicle_submissions = VehicleSubmissionSerializer(many=True, read_only=True)

    class Meta:
        model = Driver
        fields = [
            'id', 'full_name', 'email', 'phone_number', 'photo', 'years_of_experience',
            'bio', 'rating', 'is_away', 'away_reason', 'cash_payments_enabled',
            'vehicles', 'vehicle_submissions',
        ]
        read_only_fields = [
            'full_name', 'email', 'phone_number', 'photo', 'years_of_experience', 'bio', 'rating',
            'cash_payments_enabled',
        ]


class DriverAwaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = ['is_away', 'away_reason']


class DriverApplicationSerializer(serializers.ModelSerializer):
    vehicle_category = serializers.SlugRelatedField(slug_field='slug', queryset=VehicleCategory.objects.all())
    vehicle_category_name = serializers.CharField(source='vehicle_category.name', read_only=True)

    class Meta:
        model = DriverApplication
        fields = [
            'id', 'full_name', 'email', 'phone_number', 'years_of_experience', 'bio',
            'license_number', 'license_document',
            'vehicle_name', 'vehicle_category', 'vehicle_category_name', 'passenger_capacity', 'price_per_day',
            'vehicle_photo', 'vehicle_logbook_document',
            'status', 'created_at',
        ]
        read_only_fields = ['status', 'created_at']
