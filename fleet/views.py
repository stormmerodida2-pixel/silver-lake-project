from rest_framework import permissions, viewsets

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
