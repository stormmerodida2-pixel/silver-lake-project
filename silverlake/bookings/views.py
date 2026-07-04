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


from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from payments.models import DriverPayout
from .emails import send_trip_completed_email


class DriverBookingView(APIView):
    """Public, secure endpoints for drivers using their unique driver_token."""
    permission_classes = [AllowAny]

    def get(self, request, token):
        booking = get_object_or_404(Booking, driver_token=token)
        if booking.service_type != 'with_driver':
            return Response({'detail': 'Invalid service type for driver.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking).data)

    def post(self, request, token):
        booking = get_object_or_404(Booking, driver_token=token)
        if booking.service_type != 'with_driver':
            return Response({'detail': 'Invalid service type.'}, status=status.HTTP_400_BAD_REQUEST)

        act = request.data.get('action')
        if act != 'complete':
            return Response({'detail': 'Invalid action.'}, status=status.HTTP_400_BAD_REQUEST)

        if booking.status == BookingStatus.COMPLETED:
            return Response({'detail': 'Trip is already completed.'}, status=status.HTTP_400_BAD_REQUEST)
        if booking.status == BookingStatus.CANCELLED:
            return Response({'detail': 'Cannot complete a cancelled trip.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Update booking status
        booking.status = BookingStatus.COMPLETED
        booking.save(update_fields=['status'])

        # 2. Wire driver payout immediately (Auto-disburse / mark as paid)
        payout, created = DriverPayout.objects.get_or_create(
            booking=booking,
            defaults={
                'driver': booking.driver,
                'amount': booking.driver_payout_amount
            }
        )
        if not payout.is_paid:
            payout.mark_paid(reference=f'AUTO-COMPLETED-#{booking.id}')
            payout.notes = 'Payout automatically processed upon driver trip completion.'
            payout.save()

        # 3. Send review request email to customer
        send_trip_completed_email(booking)

        return Response(BookingSerializer(booking).data)

