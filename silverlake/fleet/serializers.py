from rest_framework import serializers

from .models import Vehicle, VehicleCategory, VehicleImage, VehicleServiceRecord


class VehicleCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleCategory
        fields = ['id', 'name', 'slug', 'order', 'is_active']
        read_only_fields = ['slug']


class VehicleImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleImage
        fields = ['id', 'image', 'caption', 'order']


class VehicleServiceRecordSerializer(serializers.ModelSerializer):
    logged_by_name = serializers.CharField(source='logged_by.full_name', read_only=True, default=None)

    class Meta:
        model = VehicleServiceRecord
        fields = ['id', 'vehicle', 'service_date', 'notes', 'logged_by_name', 'created_at']
        read_only_fields = ['created_at']


class VehicleSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    gallery_images = VehicleImageSerializer(many=True, read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'name', 'category', 'category_name', 'tagline', 'passenger_capacity',
            'price_per_day', 'description', 'image', 'gallery_images', 'is_available',
            'allow_self_drive', 'allow_with_driver',
        ]
