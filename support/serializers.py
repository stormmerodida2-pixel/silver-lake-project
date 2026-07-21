from rest_framework import serializers

from .models import SupportTicket, SupportTicketPhoto


class SupportTicketPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportTicketPhoto
        fields = ['id', 'image']


class SupportTicketSerializer(serializers.ModelSerializer):
    """A customer's own view of their ticket - booking is restricted to one of their own (see
    validate_booking), and status/resolution fields are never directly writable (only
    MySupportTicketViewSet.reopen changes status from the customer side)."""

    booking_label = serializers.SerializerMethodField()
    photos = SupportTicketPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'booking', 'booking_label', 'category', 'subject', 'description', 'status',
            'resolution_note', 'resolved_at', 'photos', 'created_at',
        ]
        read_only_fields = ['status', 'resolution_note', 'resolved_at', 'created_at']

    def get_booking_label(self, obj):
        if not obj.booking_id:
            return None
        booking = obj.booking
        return f'{booking.vehicle.name} ({booking.start_date} to {booking.end_date})'

    def validate_booking(self, booking):
        request = self.context.get('request')
        if booking and request and booking.user_id != request.user.id:
            raise serializers.ValidationError('You can only attach one of your own bookings.')
        return booking


class AdminSupportTicketSerializer(serializers.ModelSerializer):
    customer_name = serializers.SerializerMethodField()
    customer_email = serializers.SerializerMethodField()
    booking_label = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()
    photos = SupportTicketPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            'id', 'customer_name', 'customer_email', 'booking', 'booking_label', 'category',
            'subject', 'description', 'status', 'resolution_note', 'resolved_at',
            'resolved_by_name', 'photos', 'created_at',
        ]
        read_only_fields = fields

    def get_customer_name(self, obj):
        return obj.user.get_full_name() or obj.user.email

    def get_customer_email(self, obj):
        return obj.user.email

    def get_booking_label(self, obj):
        if not obj.booking_id:
            return None
        booking = obj.booking
        return f'#{booking.pk} - {booking.vehicle.name} ({booking.start_date} to {booking.end_date})'

    def get_resolved_by_name(self, obj):
        if not obj.resolved_by_id:
            return None
        return obj.resolved_by.get_full_name() or obj.resolved_by.email
