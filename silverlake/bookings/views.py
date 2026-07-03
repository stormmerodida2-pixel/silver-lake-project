from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Booking, BookingStatus
from .serializers import BookingSerializer


class BookingViewSet(viewsets.ModelViewSet):
    """Requires login. Customers only see/manage their own bookings; staff see all."""

    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Booking.objects.all()
        return Booking.objects.filter(user=user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Lets a customer cancel their own booking (or staff, any booking)."""
        booking = self.get_object()
        if booking.status in (BookingStatus.CANCELLED, BookingStatus.COMPLETED):
            return Response(
                {'detail': f'Booking is already {booking.get_status_display().lower()}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        booking.status = BookingStatus.CANCELLED
        booking.save(update_fields=['status'])
        return Response(BookingSerializer(booking).data)
