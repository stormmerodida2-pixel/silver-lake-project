from datetime import date

from rest_framework import permissions, viewsets

from bookings.models import BLOCKING_BOOKING_STATUSES, Booking

from .models import Vehicle, VehicleCategory
from .serializers import VehicleCategorySerializer, VehicleSerializer


class VehicleCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Public read-only list of fleet types, so pages can populate category filters/dropdowns
    without needing admin auth - categories themselves are only ever added/edited/removed
    from the admin dashboard."""

    queryset = VehicleCategory.objects.all()
    serializer_class = VehicleCategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class VehicleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vehicle.objects.filter(is_available=True)
    serializer_class = VehicleSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__slug=category)

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

        # A driver-owned vehicle disappears from the public fleet while its driver is
        # marked away or has been suspended by an admin. Vehicles with no driver (company
        # fleet) are unaffected since these lookups simply don't match a null driver.
        queryset = queryset.exclude(driver__is_away=True)
        queryset = queryset.exclude(driver__is_active=False)

        return queryset
