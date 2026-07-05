from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking, BookingStatus
from bookings.serializers import BookingSerializer
from drivers.models import ApplicationStatus, Driver, DriverApplication
from drivers.serializers import DriverApplicationSerializer
from fleet.models import Vehicle, VehicleSubmission
from payments.models import DriverPayout, Payment, PaymentStatus, Refund, RefundStatus
from reviews.models import Review

from .audit import log_admin_action
from .models import AuditLog
from .permissions import IsSuperAdmin, IsSupportStaff
from .serializers import (
    AdminAuditLogSerializer,
    AdminCreateUserSerializer,
    AdminDriverPayoutSerializer,
    AdminDriverSerializer,
    AdminRefundSerializer,
    AdminReviewSerializer,
    AdminUserSerializer,
    AdminVehicleSerializer,
    AdminVehicleSubmissionSerializer,
)

User = get_user_model()

# Actions that delete records, move money, or change fleet composition/pricing -
# restricted to superusers. Everything else (viewing, day-to-day moderation) just
# needs regular staff (IsSupportStaff).
SUPERADMIN_ONLY_ACTIONS = {'create', 'update', 'partial_update', 'destroy', 'mark_paid', 'verify', 'mark_issued'}


class AdminStatsView(APIView):
    """Revenue and operational overview for the staff dashboard."""

    permission_classes = [IsSupportStaff]

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
                'away': Driver.objects.filter(is_active=True, is_away=True).count(),
            },
            'fleet': {
                'total': Vehicle.objects.count(),
                'available': Vehicle.objects.filter(is_available=True).count(),
                'unavailable': Vehicle.objects.filter(is_available=False).count(),
            },
            'reviews': {
                'pending': Review.objects.filter(is_approved=False).count(),
            },
            'refunds': {
                'pending': Refund.objects.filter(status=RefundStatus.PENDING).count(),
            },
        })


class AdminUserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Staff-only account management (list/view/create/edit/suspend/activate/delete),
    including granting/revoking staff and superadmin roles.

    Create, edit, and delete are superadmin-only; support staff can list/view/suspend/activate."""

    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdminUserSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    def get_serializer_class(self):
        if self.action == 'create':
            return AdminCreateUserSerializer
        return AdminUserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        old_is_staff = serializer.instance.is_staff
        old_is_superuser = serializer.instance.is_superuser
        user = serializer.save()
        if user.is_staff != old_is_staff or user.is_superuser != old_is_superuser:
            log_admin_action(
                self.request, 'user.update_roles', user,
                detail=f'is_staff={user.is_staff}, is_superuser={user.is_superuser}',
            )

    def perform_destroy(self, instance):
        log_admin_action(self.request, 'user.delete', instance)
        instance.delete()

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=['is_active'])
        log_admin_action(request, 'user.suspend', user)
        return Response(AdminUserSerializer(user).data)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=['is_active'])
        log_admin_action(request, 'user.activate', user)
        return Response(AdminUserSerializer(user).data)


class AdminDriverViewSet(viewsets.ModelViewSet):
    """Staff-only full management of live Driver records (suspend = set is_active False).

    Create/update/delete are superadmin-only; support staff can list/view/suspend/activate."""

    queryset = Driver.objects.all().order_by('full_name')
    serializer_class = AdminDriverSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    @action(detail=True, methods=['post'])
    def suspend(self, request, pk=None):
        from drivers.emails import send_driver_suspended_email

        driver = self.get_object()
        reason = request.data.get('reason', '')
        driver.is_active = False
        driver.suspension_reason = reason
        driver.save(update_fields=['is_active', 'suspension_reason'])
        send_driver_suspended_email(driver, reason)
        log_admin_action(request, 'driver.suspend', driver, detail=reason)
        return Response(AdminDriverSerializer(driver).data)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        driver = self.get_object()
        driver.is_active = True
        driver.suspension_reason = ''
        driver.save(update_fields=['is_active', 'suspension_reason'])
        log_admin_action(request, 'driver.activate', driver)
        return Response(AdminDriverSerializer(driver).data)

    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        """Sends (or re-sends) the driver's portal-login invite email."""
        from drivers.services import create_driver_login

        driver = self.get_object()
        if not driver.email:
            return Response(
                {'detail': 'This driver has no email on file to send an invite to.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        create_driver_login(driver)
        return Response(AdminDriverSerializer(driver).data)


class AdminVehicleSubmissionViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only review queue for vehicles drivers submit themselves via the driver portal."""

    queryset = VehicleSubmission.objects.all().select_related('driver')
    serializer_class = AdminVehicleSubmissionSerializer
    permission_classes = [IsSupportStaff]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        submission = self.get_object()
        submission.approve()
        return Response(AdminVehicleSubmissionSerializer(submission).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        submission = self.get_object()
        submission.reject(notes=request.data.get('notes', ''))
        return Response(AdminVehicleSubmissionSerializer(submission).data)


class AdminDriverApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only review queue for 'become a driver' submissions. Approving/rejecting is
    day-to-day onboarding work, open to support staff."""

    queryset = DriverApplication.objects.all()
    serializer_class = DriverApplicationSerializer
    permission_classes = [IsSupportStaff]

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
    """Staff-only booking oversight, plus the ability to move a booking to any status -
    day-to-day operations work, open to support staff."""

    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [IsSupportStaff]

    @action(detail=True, methods=['post'], url_path='set-status')
    def set_status(self, request, pk=None):
        booking = self.get_object()
        new_status = request.data.get('status')
        if new_status not in BookingStatus.values:
            return Response(
                {'detail': f'Invalid status. Choose one of: {", ".join(BookingStatus.values)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Guard: Cannot complete with outstanding balance
        if new_status == BookingStatus.COMPLETED and booking.balance_due > 0:
            return Response(
                {'detail': f'Cannot complete trip. There is an outstanding balance of KES {booking.balance_due:,.2f}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_status == BookingStatus.CANCELLED:
            from django.core.exceptions import ValidationError as DjangoValidationError
            try:
                booking.mark_cancelled()
            except DjangoValidationError as exc:
                return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)
            return Response(BookingSerializer(booking).data)

        booking.status = new_status
        booking.save(update_fields=['status'])

        # Trigger completion email/review invite
        if new_status == BookingStatus.COMPLETED:
            from bookings.emails import send_trip_completed_email
            send_trip_completed_email(booking)

        return Response(BookingSerializer(booking).data)




class AdminDriverPayoutViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-only view of what's owed to drivers. Everyone can see the ledger; only
    superadmins can actually mark a payout as disbursed, since that's real money moving."""

    queryset = DriverPayout.objects.all().select_related('driver', 'booking').order_by('is_paid', '-created_at')
    serializer_class = AdminDriverPayoutSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        payout = self.get_object()
        if payout.is_voided:
            return Response(
                {'detail': 'This payout was voided because the booking was cancelled.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if payout.needs_verification and not payout.is_verified:
            return Response(
                {'detail': 'This payout was confirmed via a self-reported cash payment and must be verified before it can be marked paid.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payout.mark_paid(reference=request.data.get('payout_reference', ''))
        log_admin_action(request, 'payout.mark_paid', payout, detail=request.data.get('payout_reference', ''))
        return Response(AdminDriverPayoutSerializer(payout).data)

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Confirms a cash-sourced payout is legitimate (e.g. after reconciling with the driver
        or customer) so it becomes eligible to be marked paid."""
        payout = self.get_object()
        payout.verify()
        log_admin_action(request, 'payout.verify', payout)
        return Response(AdminDriverPayoutSerializer(payout).data)


class AdminAuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only trail of who performed sensitive admin actions (role changes, suspensions,
    payouts, refunds). Viewing is not itself destructive, so any staff account can see it."""

    queryset = AuditLog.objects.all().select_related('actor')
    serializer_class = AdminAuditLogSerializer
    permission_classes = [IsSupportStaff]


class AdminRefundViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-only view of refunds owed after a cancelled booking. Everyone can see the ledger;
    only superadmins can mark one issued, since that's real money moving."""

    queryset = Refund.objects.all().select_related('booking').order_by('status', '-created_at')
    serializer_class = AdminRefundSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    @action(detail=True, methods=['post'], url_path='mark-issued')
    def mark_issued(self, request, pk=None):
        refund = self.get_object()
        refund.mark_issued(reference=request.data.get('reference', ''))
        log_admin_action(request, 'refund.mark_issued', refund, detail=request.data.get('reference', ''))
        return Response(AdminRefundSerializer(refund).data)


class AdminFleetViewSet(viewsets.ModelViewSet):
    """Staff-only full CRUD for Vehicle records, plus toggle availability.

    Create/update/delete (fleet composition and pricing) are superadmin-only; support
    staff can list/view/toggle availability."""

    queryset = Vehicle.objects.all().order_by('name')
    serializer_class = AdminVehicleSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    @action(detail=True, methods=['post'], url_path='toggle-availability')
    def toggle_availability(self, request, pk=None):
        vehicle = self.get_object()
        vehicle.is_available = not vehicle.is_available
        vehicle.save(update_fields=['is_available'])
        return Response(AdminVehicleSerializer(vehicle).data)


class AdminReviewViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Staff-only review moderation. Approve/reject is day-to-day moderation (support staff);
    permanently deleting a review is superadmin-only."""

    queryset = Review.objects.all().order_by('-created_at')
    serializer_class = AdminReviewSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        review = self.get_object()
        review.is_approved = True
        review.save(update_fields=['is_approved'])
        return Response(AdminReviewSerializer(review).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject = mark unapproved (keep record but hide from public)."""
        review = self.get_object()
        review.is_approved = False
        review.save(update_fields=['is_approved'])
        return Response(AdminReviewSerializer(review).data)
