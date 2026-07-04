from rest_framework import serializers

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id', 'customer_name', 'rating', 'comment', 'driver_name', 'created_at']
        read_only_fields = ['created_at']

    def get_driver_name(self, obj):
        return obj.driver.full_name if obj.driver_id else None


class BookingReviewCreateSerializer(serializers.ModelSerializer):
    """Used when a customer reviews one of their own completed trips - booking, driver, and
    customer_name are filled in by the view, not the client."""

    class Meta:
        model = Review
        fields = ['rating', 'comment']
