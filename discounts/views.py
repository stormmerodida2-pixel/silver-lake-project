from rest_framework import viewsets

from core.audit import log_admin_action
from core.permissions import IsPlatformSuperAdmin

from .models import DiscountCode
from .serializers import AdminDiscountCodeSerializer


class AdminDiscountCodeViewSet(viewsets.ModelViewSet):
    """Lets a SilverLake superadmin generate and manage single-use booking discount codes - not
    delegated to a FleetPartner's own org-admin (see IsPlatformSuperAdmin), since a code
    discounts SilverLake's own platform-wide total_amount (and, downstream, whichever
    partner/driver happens to get booked), not something scoped to one partner's own fleet."""

    serializer_class = AdminDiscountCodeSerializer
    permission_classes = [IsPlatformSuperAdmin]
    queryset = DiscountCode.objects.select_related('created_by', 'redeemed_booking')

    def perform_create(self, serializer):
        discount_code = serializer.save(created_by=self.request.user)
        log_admin_action(self.request, 'discountcode.create', discount_code, detail=discount_code.code)

    def perform_update(self, serializer):
        discount_code = serializer.save()
        log_admin_action(self.request, 'discountcode.update', discount_code, detail=discount_code.code)

    def perform_destroy(self, instance):
        log_admin_action(self.request, 'discountcode.delete', instance, detail=instance.code)
        instance.delete()
