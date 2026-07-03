from datetime import date

from rest_framework import viewsets

from bookings.models import BLOCKING_BOOKING_STATUSES, Booking

from .models import Vehicle
from .serializers import VehicleSerializer


class VehicleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vehicle.objects.filter(is_available=True)
    serializer_class = VehicleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)

        today = date.today()
        currently_booked_ids = Booking.objects.filter(
            status__in=BLOCKING_BOOKING_STATUSES,
            start_date__lte=today,
            end_date__gte=today,
        ).values_list('vehicle_id', flat=True)
        queryset = queryset.exclude(id__in=currently_booked_ids)

        # Only exclude on an actually-lapsed date; vehicles with no insurance/inspection
        # date recorded yet aren't hidden, so this doesn't break existing fleet entries.
        queryset = queryset.exclude(insurance_expiry_date__lt=today)
        queryset = queryset.exclude(inspection_expiry_date__lt=today)

        return queryset
