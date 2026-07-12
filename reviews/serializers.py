from rest_framework import serializers

from .models import Review


class ReviewSerializer(serializers.ModelSerializer):
    """Public-facing shape - deliberately excludes which driver/booking a review is about.
    Admin moderation uses its own separate serializer (core.serializers.AdminReviewSerializer)
    that does include the driver, since staff need that to moderate accurately."""

    class Meta:
        model = Review
        fields = ['id', 'customer_name', 'rating', 'comment', 'created_at']
        read_only_fields = ['created_at']


class BookingReviewCreateSerializer(serializers.ModelSerializer):
    """Used when a customer reviews one of their own completed trips - booking, driver, and
    customer_name are filled in by the view, not the client."""

    class Meta:
        model = Review
        fields = ['rating', 'comment']
