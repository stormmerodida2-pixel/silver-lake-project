from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from bookings.models import BLOCKING_BOOKING_STATUSES, Booking

from .models import Vehicle, VehicleCategory, visible_vehicles
from .serializers import VehicleCategorySerializer, VehicleSerializer


class VehicleCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Public read-only list of fleet types, so pages can populate category filters/dropdowns
    without needing admin auth - categories themselves are only ever added/edited/removed
    from the admin dashboard. Only active types are offered here; a retired type still works
    fine for vehicles/applications already using it, it just can't be newly selected."""

    queryset = VehicleCategory.objects.filter(is_active=True)
    serializer_class = VehicleCategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class VehicleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vehicle.objects.filter(is_available=True).select_related('category')
    serializer_class = VehicleSerializer

    def get_queryset(self):
        queryset = visible_vehicles().select_related('category')
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__slug=category)
        return queryset

    @action(detail=True, methods=['get'])
    def availability(self, request, pk=None):
        """Booked date ranges for this vehicle from today onward, so the booking form can warn
        about a conflict before the customer submits - mirrors the exact same overlap window
        Booking.clean() enforces server-side (BLOCKING_BOOKING_STATUSES), so a date the customer
        sees as free here is actually free. Deliberately not self.get_object() - that's scoped
        to visible_vehicles(), which excludes a vehicle currently mid-booking, exactly the
        vehicle whose future availability is most worth showing."""
        vehicle = get_object_or_404(Vehicle, pk=pk)
        bookings = Booking.objects.filter(
            vehicle=vehicle, status__in=BLOCKING_BOOKING_STATUSES, end_date__gte=date.today(),
        ).values('start_date', 'end_date').order_by('start_date')
        return Response(list(bookings))
