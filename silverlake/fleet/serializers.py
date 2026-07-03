from rest_framework import serializers

from .models import Vehicle, VehicleImage


class VehicleImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleImage
        fields = ['id', 'image', 'caption', 'order']


class VehicleSerializer(serializers.ModelSerializer):
    gallery_images = VehicleImageSerializer(many=True, read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            'id', 'name', 'category', 'tagline', 'passenger_capacity',
            'price_per_day', 'description', 'image', 'gallery_images', 'is_available',
            'allow_self_drive', 'allow_with_driver',
        ]
