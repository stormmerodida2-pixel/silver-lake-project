from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking, BookingStatus
from bookings.serializers import BookingSerializer
from drivers.models import ApplicationStatus, Driver, DriverApplication
from drivers.serializers import DriverApplicationSerializer
from payments.models import DriverPayout, Payment, PaymentStatus

from .serializers import AdminDriverPayoutSerializer, AdminDriverSerializer, AdminUserSerializer

User = get_user_model()


class AdminStatsView(APIView):
    """Revenue and operational overview for the staff dashboard."""

    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        successful_payments = Payment.objects.filter(status=PaymentStatus.SUCCESSFUL)
        total_revenue = successful_payments.aggregate(total=Sum('amount'))['total'] or 0
        revenue_this_month = successful_payments.filter(created_at__gte=month_start).aggregate(
            total=Sum('amount')
        )['total'] or 0

        confirmed_or_later = Booking.objects.exclude(status=BookingStatus.CANCELLED)
        platform_fees_earned = sum(
            (b.platform_fee_amount for b in confirmed_or_later.exclude(status=BookingStatus.PENDING)),
            start=0,
        )

        payouts_owed = DriverPayout.objects.filter(is_paid=False).aggregate(total=Sum('amount'))['total'] or 0
        payouts_paid = DriverPayout.objects.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or 0

        bookings_by_status = dict(
            Booking.objects.values_list('status').annotate(count=Count('id')).order_by()
        )

        return Response({
            'revenue': {
                'total_collected': total_revenue,
                'collected_this_month': revenue_this_month,
                'platform_fees_earned': platform_fees_earned,
                'driver_payouts_owed': payouts_owed,
                'driver_payouts_paid': payouts_paid,
            },
            'bookings': {
                'by_status': bookings_by_status,
                'total': Booking.objects.count(),
            },
            'users': {
                'total': User.objects.count(),
                'active': User.objects.filter(is_active=True).count(),
                'new_last_7_days': User.objects.filter(date_joined__gte=now - timedelta(days=7)).count(),
            },
            'drivers': {
                'pending_applications': DriverApplication.objects.filter(
                    status=ApplicationStatus.PENDING
                ).count(),
            },
        })


class AdminUserViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Staff-only customer account management (list/view/suspend/activate/delete). Staff/superuser
    accounts aren't manageable through this API - use Django admin for those."""

    queryset = User.objects.filter(is_staff=False).order_by('-date_joined')
    serializer_class = AdminUserSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response(AdminUserSerializer(user).data)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        return Response(AdminUserSerializer(user).data)


class AdminDriverViewSet(viewsets.ModelViewSet):
    """Staff-only full management of live Driver records (suspend = set is_active False)."""

    queryset = Driver.objects.all().order_by('full_name')
    serializer_class = AdminDriverSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        driver = self.get_object()
        driver.is_active = False
        driver.save(update_fields=['is_active'])
        return Response(AdminDriverSerializer(driver).data)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        driver = self.get_object()
        driver.is_active = True
        driver.save(update_fields=['is_active'])
        return Response(AdminDriverSerializer(driver).data)


class AdminDriverApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only review queue for 'become a driver' submissions."""

    queryset = DriverApplication.objects.all()
    serializer_class = DriverApplicationSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        application = self.get_object()
        application.approve()
        return Response(DriverApplicationSerializer(application).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        application = self.get_object()
        application.reject(notes=request.data.get('notes', ''))
        return Response(DriverApplicationSerializer(application).data)


class AdminBookingViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only booking oversight, plus the ability to move a booking to any status."""

    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=True, methods=['post'], url_path='set-status')
    def set_status(self, request, pk=None):
        booking = self.get_object()
        new_status = request.data.get('status')
        if new_status not in BookingStatus.values:
            return Response(
                {'detail': f'Invalid status. Choose one of: {", ".join(BookingStatus.values)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        booking.status = new_status
        booking.save(update_fields=['status'])
        return Response(BookingSerializer(booking).data)


class AdminDriverPayoutViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-only view of what's owed to drivers, with a 'mark as paid' action once disbursed."""

    queryset = DriverPayout.objects.all().select_related('driver', 'booking').order_by('is_paid', '-created_at')
    serializer_class = AdminDriverPayoutSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        payout = self.get_object()
        payout.mark_paid(reference=request.data.get('payout_reference', ''))
        return Response(AdminDriverPayoutSerializer(payout).data)
