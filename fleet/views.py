from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from bookings.models import BLOCKING_BOOKING_STATUSES, Booking, WaitlistEntry
from bookings.serializers import WaitlistEntrySerializer

from .models import FavoriteVehicle, Vehicle, VehicleCategory, visible_vehicles
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

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            try:
                start = date.fromisoformat(start_date)
                end = date.fromisoformat(end_date)
            except ValueError:
                return queryset
            if end < start:
                return queryset
            # Same overlap window Booking.clean() and the availability action both use - a
            # vehicle only counts as unavailable for a search if an actual blocking booking
            # overlaps the requested range.
            conflicting_vehicle_ids = Booking.objects.filter(
                status__in=BLOCKING_BOOKING_STATUSES, start_date__lte=end, end_date__gte=start,
            ).values_list('vehicle_id', flat=True)
            queryset = queryset.exclude(id__in=conflicting_vehicle_ids)

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

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def toggle_favorite(self, request, pk=None):
        """Bookmarks/un-bookmarks this vehicle for the logged-in customer - a pure browsing
        convenience, no effect on booking or availability. Not scoped to visible_vehicles() for
        the same reason the availability action isn't - a customer should still be able to
        un-favorite a car that's since become temporarily unavailable."""
        vehicle = get_object_or_404(Vehicle, pk=pk)
        favorite, created = FavoriteVehicle.objects.get_or_create(user=request.user, vehicle=vehicle)
        if not created:
            favorite.delete()
        return Response({'is_favorited': created})

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def favorites(self, request):
        """The logged-in customer's saved vehicles, most recently favorited first - shown
        regardless of current availability (still useful to see what you saved even if it's
        momentarily booked), unlike the main listing's visible_vehicles() scoping."""
        vehicles = Vehicle.objects.filter(favorited_by__user=request.user).select_related('category').order_by(
            '-favorited_by__created_at'
        )
        serializer = self.get_serializer(vehicles, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post', 'delete'], permission_classes=[permissions.IsAuthenticated])
    def waitlist(self, request, pk=None):
        """Lets a customer ask to be emailed the moment this vehicle opens up for a date range
        that's currently blocked by another booking - see
        bookings.services.notify_waitlist_for_freed_dates. Not self.get_object() for the same
        reason availability() isn't - a vehicle worth waitlisting for is exactly one
        visible_vehicles() might exclude for being mid-booking right now."""
        vehicle = get_object_or_404(Vehicle, pk=pk)
        try:
            start = date.fromisoformat(request.data.get('start_date') or '')
            end = date.fromisoformat(request.data.get('end_date') or '')
        except ValueError:
            return Response({'detail': 'A valid start_date and end_date are required.'}, status=400)
        if end < start:
            return Response({'detail': 'End date cannot be before start date.'}, status=400)

        if request.method == 'DELETE':
            WaitlistEntry.objects.filter(vehicle=vehicle, user=request.user, start_date=start, end_date=end).delete()
            return Response(status=204)

        if start < date.today():
            return Response({'detail': 'Start date cannot be in the past.'}, status=400)

        conflict = Booking.objects.filter(
            vehicle=vehicle, status__in=BLOCKING_BOOKING_STATUSES, start_date__lte=end, end_date__gte=start,
        ).exists()
        if not conflict:
            return Response(
                {'detail': 'This vehicle is already available for these dates - you can book it directly.'},
                status=400,
            )

        entry, _ = WaitlistEntry.objects.get_or_create(
            vehicle=vehicle, user=request.user, start_date=start, end_date=end,
        )
        return Response(WaitlistEntrySerializer(entry, context={'request': request}).data, status=201)

    @action(detail=False, methods=['get'], url_path='waitlist', permission_classes=[permissions.IsAuthenticated])
    def my_waitlist(self, request):
        """The logged-in customer's own waitlist entries, most recent first."""
        entries = WaitlistEntry.objects.filter(user=request.user).select_related('vehicle')
        return Response(WaitlistEntrySerializer(entries, many=True, context={'request': request}).data)
