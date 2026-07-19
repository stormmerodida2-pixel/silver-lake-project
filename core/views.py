from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, ProtectedError, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.serializers import UserSerializer
from accounts.services import get_or_create_customer_account
from bookings.models import Booking, BookingSource, BookingStatus
from bookings.serializers import AdminGovernmentBookingSerializer, BookingSerializer
from drivers.models import ApplicationStatus, Driver, DriverApplication
from drivers.serializers import DriverApplicationSerializer
from fleet.models import FleetPartner, Vehicle, VehicleCategory, VehicleImage, VehicleServiceRecord, VehicleSubmission
from fleet.serializers import VehicleCategorySerializer, VehicleImageSerializer, VehicleServiceRecordSerializer
from payments.models import DriverPayout, Payment, PaymentMethod, PaymentStatus, Refund, RefundStatus
from reviews.models import Review

from .audit import log_admin_action
from .models import AuditLog
from .permissions import IsPlatformStaff, IsPlatformSuperAdmin, IsSuperAdmin, IsSupportStaff, get_user_organization
from .serializers import (
    AdminAuditLogSerializer,
    AdminCreateUserSerializer,
    AdminDriverPayoutSerializer,
    AdminDriverSerializer,
    AdminFleetPartnerSerializer,
    AdminRefundSerializer,
    AdminReferralSettingsSerializer,
    AdminReviewSerializer,
    AdminUserSerializer,
    AdminVehicleSerializer,
    AdminVehicleSubmissionSerializer,
)
from .utils import capture_replaced_files, delete_files, parse_amount, search_filter

User = get_user_model()

# Actions that delete records, move money, or change fleet composition/pricing -
# restricted to superusers. Everything else (viewing, day-to-day moderation) just
# needs regular staff (IsSupportStaff).
SUPERADMIN_ONLY_ACTIONS = {
    'create', 'update', 'partial_update', 'destroy', 'mark_paid', 'verify', 'mark_issued',
    'add_gallery_images', 'remove_gallery_image', 'add_service_record', 'invite_staff',
}

# Mirrors payments.views.REMINDER_COOLDOWN - long enough that it isn't spam, short enough that a
# driver who genuinely forgot can be re-poked same day.
BALANCE_REMINDER_COOLDOWN = timedelta(hours=1)


def _delete_or_block(request, instance, action, blocked_message):
    """Deletes instance, logging who did it - or returns a clean 400 instead of a raw 500 if
    it's still referenced by records (bookings, payouts) that must never silently disappear
    with it."""
    try:
        log_admin_action(request, action, instance)
        instance.delete()
    except ProtectedError:
        return Response({'detail': blocked_message}, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_204_NO_CONTENT)


class AdminStatsView(APIView):
    """Revenue and operational overview for the staff dashboard."""

    permission_classes = [IsSupportStaff]

    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        organization = get_user_organization(request.user)

        # An org-scoped requester (a FleetPartner's own admin/staff) only ever sees numbers for
        # their own organization's vehicles/bookings - never SilverLake's own or another
        # partner's. A genuine SilverLake platform account sees everything, unchanged.
        payments_qs = Payment.objects.filter(status=PaymentStatus.SUCCESSFUL)
        bookings_qs = Booking.objects.all()
        payouts_qs = DriverPayout.objects.all()
        vehicles_qs = Vehicle.objects.all()
        reviews_qs = Review.objects.all()
        refunds_qs = Refund.objects.all()
        users_qs = User.objects.all()
        if organization is not None:
            payments_qs = payments_qs.filter(booking__vehicle__owner=organization)
            bookings_qs = bookings_qs.filter(vehicle__owner=organization)
            payouts_qs = payouts_qs.filter(booking__vehicle__owner=organization)
            vehicles_qs = vehicles_qs.filter(owner=organization)
            reviews_qs = reviews_qs.filter(booking__vehicle__owner=organization)
            refunds_qs = refunds_qs.filter(booking__vehicle__owner=organization)
            users_qs = users_qs.filter(staff_organization__organization=organization)

        total_revenue = payments_qs.aggregate(total=Sum('amount'))['total'] or 0
        revenue_this_month = payments_qs.filter(created_at__gte=month_start).aggregate(
            total=Sum('amount')
        )['total'] or 0

        confirmed_or_later = bookings_qs.exclude(status=BookingStatus.CANCELLED)
        platform_fees_earned = sum(
            (b.platform_fee_amount for b in confirmed_or_later.exclude(status=BookingStatus.PENDING)),
            start=0,
        )

        payouts_owed = payouts_qs.filter(is_paid=False).aggregate(total=Sum('amount'))['total'] or 0
        payouts_paid = payouts_qs.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or 0

        bookings_by_status = dict(
            bookings_qs.values_list('status').annotate(count=Count('id')).order_by()
        )

        # A genuine SilverLake platform superadmin only - never an org-admin, who'd otherwise see
        # every other organization's (and SilverLake's own) Paybill credentials and revenue.
        fleet_partners = []
        if request.user.is_superuser and organization is None:
            live_bookings = Booking.objects.exclude(status=BookingStatus.CANCELLED)
            for partner in FleetPartner.objects.filter(is_active=True).order_by('name'):
                partner_bookings = live_bookings.filter(vehicle__owner=partner)
                partner_revenue = partner_bookings.aggregate(total=Sum('total_amount'))['total'] or 0
                partner_collected = Payment.objects.filter(
                    status=PaymentStatus.SUCCESSFUL, booking__vehicle__owner=partner,
                ).exclude(booking__status=BookingStatus.CANCELLED).aggregate(total=Sum('amount'))['total'] or 0
                # SilverLake's own cut, kept as revenue. The remainder is owed BACK to the
                # partner via a real DriverPayout (organization=partner, see
                # Booking._ensure_driver_payout) - money currently still lands in SilverLake's
                # own Paybill regardless of ownership, so this is a real payable, not a
                # speculative estimate.
                platform_fee_earned = (Decimal(partner_collected) * partner.platform_fee_percent / Decimal('100')).quantize(Decimal('0.01'))
                partner_payouts = DriverPayout.objects.filter(organization=partner)
                payout_owed = partner_payouts.filter(is_paid=False).aggregate(total=Sum('amount'))['total'] or 0
                payout_paid = partner_payouts.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or 0
                fleet_partners.append({
                    'id': partner.id,
                    'name': partner.name,
                    'vehicle_count': partner.vehicles.count(),
                    'bookings_count': partner_bookings.count(),
                    'total_revenue': partner_revenue,
                    'total_collected': partner_collected,
                    'platform_fee_earned': platform_fee_earned,
                    'payout_owed': payout_owed,
                    'payout_paid': payout_paid,
                })

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
                'total': bookings_qs.count(),
                'needing_attention': bookings_qs.filter(
                    status__in=(BookingStatus.CONFIRMED, BookingStatus.ONGOING),
                    end_date__lt=timezone.localdate(),
                ).count(),
            },
            'users': {
                'total': users_qs.count(),
                'active': users_qs.filter(is_active=True).count(),
                'new_last_7_days': users_qs.filter(date_joined__gte=now - timedelta(days=7)).count(),
            },
            'drivers': {
                # SilverLake's own onboarding pipeline - not meaningful for a single organization.
                'pending_applications': 0 if organization is not None else DriverApplication.objects.filter(
                    status=ApplicationStatus.PENDING
                ).count(),
                'away': Driver.objects.filter(
                    id__in=vehicles_qs.exclude(driver__isnull=True).values('driver_id'),
                    is_active=True, is_away=True,
                ).count() if organization is not None else Driver.objects.filter(is_active=True, is_away=True).count(),
            },
            'fleet': {
                'total': vehicles_qs.count(),
                'available': vehicles_qs.filter(is_available=True).count(),
                'unavailable': vehicles_qs.filter(is_available=False).count(),
                # is_service_due is time-based off the latest VehicleServiceRecord (or the
                # vehicle's created_at if never serviced) - not a single DB column, so this has
                # to be counted in Python rather than a queryset .filter()/.count().
                'service_due': sum(
                    1 for v in vehicles_qs.prefetch_related('service_records') if v.is_service_due
                ),
            },
            'reviews': {
                'pending': reviews_qs.filter(is_approved=False).count(),
            },
            'refunds': {
                'pending': refunds_qs.filter(status=RefundStatus.PENDING).count(),
            },
            'fleet_partners': fleet_partners,
        })


class AdminHealthView(APIView):
    """Lets staff see whether the app's own dependencies are actually working right now -
    database, email, M-Pesa, file storage, the background sweep thread - without needing
    someone to SSH into the server and check by hand. Read-only and non-destructive, so any
    staff tier can view it, same as AdminStatsView."""

    permission_classes = [IsSupportStaff]

    def get(self, request):
        from decouple import config as env_config
        from django.conf import settings
        from django.db import connection

        from payments import scheduler

        checks = {}

        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            checks['database'] = {'ok': True, 'engine': connection.vendor}
        except Exception as exc:
            checks['database'] = {'ok': False, 'engine': connection.vendor, 'error': str(exc)}

        email_configured = bool(settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)
        checks['email'] = {
            'ok': email_configured,
            'backend': settings.EMAIL_BACKEND.rsplit('.', 1)[-1],
            'detail': 'Sending via real SMTP' if email_configured else 'Falling back to sent_emails/ - not actually sending',
        }

        # MPESA_*/AWS_* aren't Django settings attributes at all - payments/mpesa.py and
        # settings/production.py both read them straight from decouple.config(), so check the
        # same env vars they actually use rather than something that was never set here.
        mpesa_env = env_config('MPESA_ENV', default='sandbox')
        mpesa_configured = bool(env_config('MPESA_CONSUMER_KEY', default='') and env_config('MPESA_PASSKEY', default=''))
        checks['mpesa'] = {
            'ok': mpesa_configured,
            'environment': mpesa_env,
            'detail': f'{mpesa_env.capitalize()} credentials configured' if mpesa_configured else 'No credentials configured',
        }

        s3_bucket = env_config('AWS_STORAGE_BUCKET_NAME', default='')
        checks['storage'] = {
            'ok': True,
            'backend': 's3' if s3_bucket else 'local disk',
            'detail': f'Bucket: {s3_bucket}' if s3_bucket else 'Not persistent across redeploys on most hosts',
        }

        if scheduler.last_tick_at is None:
            checks['scheduler'] = {
                'ok': scheduler.is_running(),
                'detail': 'Started, waiting for first tick' if scheduler.is_running() else 'Not running',
            }
        else:
            seconds_since = (timezone.now() - scheduler.last_tick_at).total_seconds()
            checks['scheduler'] = {
                'ok': seconds_since < scheduler.SWEEP_INTERVAL_SECONDS * 2,
                'detail': f'Last tick {int(seconds_since)}s ago',
            }

        checks['debug_mode'] = {'ok': not settings.DEBUG, 'detail': 'DEBUG is on' if settings.DEBUG else 'DEBUG is off'}

        return Response(checks)


class AdminReferralSettingsView(APIView):
    """Lets a platform superadmin see and change the referral program's KES credit amount and
    at-a-glance stats - platform-wide, not org-scoped, since the referral program itself isn't
    something a FleetPartner's own org-admin can configure (matches other platform-wide
    taxonomy, e.g. AdminFleetPartnerViewSet itself)."""

    permission_classes = [IsPlatformSuperAdmin]

    def get(self, request):
        from accounts.models import ReferralCredit, ReferralSettings

        settings_row, _ = ReferralSettings.objects.get_or_create(pk=ReferralSettings.SINGLETON_ID)
        awarded = ReferralCredit.objects.aggregate(count=Count('id'), total=Sum('amount'))
        redeemed = ReferralCredit.objects.filter(redeemed_booking__isnull=False).aggregate(
            count=Count('id'), total=Sum('amount'),
        )
        outstanding = ReferralCredit.objects.filter(redeemed_booking__isnull=True).aggregate(total=Sum('amount'))

        return Response({
            **AdminReferralSettingsSerializer(settings_row).data,
            'credits_awarded_count': awarded['count'] or 0,
            'credits_awarded_total': awarded['total'] or Decimal('0'),
            'credits_redeemed_count': redeemed['count'] or 0,
            'credits_redeemed_total': redeemed['total'] or Decimal('0'),
            'credits_outstanding_total': outstanding['total'] or Decimal('0'),
        })

    def patch(self, request):
        from accounts.models import ReferralSettings

        settings_row, _ = ReferralSettings.objects.get_or_create(pk=ReferralSettings.SINGLETON_ID)
        serializer = AdminReferralSettingsSerializer(settings_row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_admin_action(request, 'referral_settings.update', settings_row, detail=f'credit_amount={settings_row.credit_amount}')
        return self.get(request)


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
        # Stricter than the rest of this viewset's SUPERADMIN_ONLY_ACTIONS (which also allow a
        # FleetPartner's own org-admin) - impersonation lets the actor act as literally any
        # customer/driver platform-wide, not just within their own organization's scope, so it's
        # reserved for a genuine SilverLake superadmin only.
        if self.action == 'impersonate':
            return [IsPlatformSuperAdmin()]
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        if organization is None:
            queryset = self.queryset
        else:
            # An org-admin manages their own organization's staff here, not customers (a
            # customer isn't scoped to any one organization - they can book from any partner's
            # fleet) and not any other organization's or SilverLake's own staff.
            queryset = self.queryset.filter(staff_organization__organization=organization)

        params = self.request.query_params
        queryset = search_filter(queryset, params.get('search', '').strip(), ['first_name', 'last_name', 'email'])
        role = params.get('role', '').strip()
        if role == 'customer':
            queryset = queryset.filter(is_staff=False)
        elif role == 'staff':
            queryset = queryset.filter(is_staff=True, is_superuser=False)
        elif role == 'superadmin':
            queryset = queryset.filter(is_superuser=True)
        return queryset

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

    def destroy(self, request, *args, **kwargs):
        return _delete_or_block(
            request, self.get_object(), 'user.delete',
            'This user has bookings on file and cannot be deleted. Suspend the account instead.',
        )

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

    @action(detail=True, methods=['post'])
    def impersonate(self, request, pk=None):
        """Issues a fresh token pair for this user so a superadmin can act as them for support
        purposes - never for another staff/superadmin account (blocked below; get_permissions()
        also keeps this off-limits to a FleetPartner's own org-admin entirely). The refresh
        token is deliberately much shorter-lived than a normal login's 14 days, so a forgotten/
        abandoned impersonation session can't linger anywhere near that long. Returns the same
        {access, refresh, user} shape as a normal login, via the same UserSerializer the app's
        own session state already expects everywhere else - not AdminUserSerializer's shape,
        since the frontend runs as this user afterward, not as an admin viewing them.

        A driver target gets a read-only session instead of full access (see
        drivers.permissions.IsDriverUser) - acknowledging a booking, starting/ending a trip, or
        declaring a payment is meant to mean the driver themselves actually did it, and letting
        a superadmin do those things "as" the driver would quietly break that meaning. The access
        token's own lifetime is stretched to match the refresh token's here (rather than the
        usual 15 minutes) specifically so this never needs a mid-session refresh - the stock
        token-refresh endpoint doesn't carry custom claims like this one over to the new access
        token it mints, which would silently turn a read-only session back into a full one."""
        target = self.get_object()
        if target.is_staff or target.is_superuser:
            return Response(
                {'detail': 'Cannot impersonate a staff or superadmin account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_driver_target = bool(getattr(target, 'driver_profile', None) and target.driver_profile.is_active)

        refresh = RefreshToken.for_user(target)
        refresh.set_exp(lifetime=timedelta(hours=2))
        refresh['impersonated_by'] = request.user.id
        access = refresh.access_token
        access['impersonated_by'] = request.user.id
        if is_driver_target:
            refresh['read_only'] = True
            access['read_only'] = True
            access.set_exp(lifetime=timedelta(hours=2))

        log_admin_action(request, 'user.impersonate', target, detail=f'By {request.user.email}')
        return Response({
            'access': str(access),
            'refresh': str(refresh),
            'user': UserSerializer(target, context={'request': request}).data,
        })

    @action(detail=False, methods=['post'], url_path='invite-staff')
    def invite_staff(self, request):
        """Invites a new staff account and emails them a way to set their password - a
        SilverLake superadmin invites their own team; an org-admin invites their own
        organization's staff (forced, regardless of what's submitted - never a different org,
        never SilverLake's own team)."""
        from .services import invite_staff_account

        email = request.data.get('email', '').strip()
        if not email:
            return Response({'email': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)

        organization = get_user_organization(request.user)
        user = invite_staff_account(
            email, organization=organization, is_superuser=bool(request.data.get('is_superuser')),
            first_name=request.data.get('first_name', ''), last_name=request.data.get('last_name', ''),
        )
        log_admin_action(request, 'user.invite_staff', user, detail=f'organization={organization}')
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminDriverViewSet(viewsets.ModelViewSet):
    """Staff-only full management of live Driver records (suspend = set is_active False).

    Create/update/delete are superadmin-only; support staff can list/view/suspend/activate."""

    queryset = Driver.objects.all().order_by('full_name')
    serializer_class = AdminDriverSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        if organization is None:
            queryset = self.queryset
        else:
            # Driver has no organization field of its own - scoped via which vehicle(s) they
            # actually drive for this org. distinct() since a driver could in principle be linked
            # to more than one of the org's vehicles.
            queryset = self.queryset.filter(vehicles__owner=organization).distinct()

        params = self.request.query_params
        return search_filter(queryset, params.get('search', '').strip(), ['full_name', 'email', 'phone_number'])

    def perform_update(self, serializer):
        old_files = capture_replaced_files(serializer, ['photo'])
        serializer.save()
        delete_files(old_files)

    def destroy(self, request, *args, **kwargs):
        return _delete_or_block(
            request, self.get_object(), 'driver.delete',
            'This driver has payout records on file and cannot be deleted. Suspend the account instead.',
        )

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

    queryset = VehicleSubmission.objects.all().select_related('driver', 'category')
    serializer_class = AdminVehicleSubmissionSerializer
    # SilverLake's own individual driver-partner onboarding pipeline - unrelated to any
    # FleetPartner organization, so no org staff account should see it.
    permission_classes = [IsPlatformStaff]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        submission = self.get_object()
        submission.approve()
        log_admin_action(request, 'vehicle_submission.approve', submission)
        return Response(AdminVehicleSubmissionSerializer(submission).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        submission = self.get_object()
        notes = request.data.get('notes', '')
        submission.reject(notes=notes)
        log_admin_action(request, 'vehicle_submission.reject', submission, detail=notes)
        return Response(AdminVehicleSubmissionSerializer(submission).data)


class AdminDriverApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff-only review queue for 'become a driver' submissions. Approving/rejecting is
    day-to-day onboarding work, open to support staff."""

    queryset = DriverApplication.objects.all().select_related('vehicle_category')
    serializer_class = DriverApplicationSerializer
    # SilverLake's own individual driver-partner onboarding pipeline - unrelated to any
    # FleetPartner organization, so no org staff account should see it.
    permission_classes = [IsPlatformStaff]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        application = self.get_object()
        application.approve()
        log_admin_action(request, 'driver_application.approve', application)
        return Response(DriverApplicationSerializer(application).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        application = self.get_object()
        notes = request.data.get('notes', '')
        application.reject(notes=notes)
        log_admin_action(request, 'driver_application.reject', application, detail=notes)
        return Response(DriverApplicationSerializer(application).data)


class AdminBookingViewSet(mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Staff-only booking oversight, plus the ability to move a booking to any status -
    day-to-day operations work, open to support staff.

    Editing the record itself (driver, dates, vehicle, etc.) is superadmin-only - unlike a
    status change, it can shift who a trip's payout is attributed to, so it gets the same tier
    as other fleet/driver-composition changes. Re-runs the same conflict/capability checks as a
    normal booking via BookingSerializer.validate()."""

    queryset = Booking.objects.all()
    serializer_class = BookingSerializer

    def get_permissions(self):
        if self.action in ('update', 'partial_update'):
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        queryset = self.queryset if organization is None else self.queryset.filter(vehicle__owner=organization)

        params = self.request.query_params
        queryset = search_filter(
            queryset, params.get('search', '').strip(),
            ['customer_name', 'customer_phone', 'customer_email'],
        )
        status_param = params.get('status', '').strip()
        if status_param:
            queryset = queryset.filter(status=status_param)
        service_type = params.get('service_type', '').strip()
        if service_type:
            queryset = queryset.filter(service_type=service_type)
        return queryset

    def perform_update(self, serializer):
        old_driver_id = serializer.instance.driver_id
        old_files = capture_replaced_files(serializer, ['customer_license_document', 'customer_id_document'])
        booking = serializer.save()
        delete_files(old_files)
        detail = f'driver: {old_driver_id or "none"} -> {booking.driver_id or "none"}' if booking.driver_id != old_driver_id else ''
        log_admin_action(self.request, 'booking.update', booking, detail=detail)

    @action(detail=True, methods=['post'], url_path='set-status')
    def set_status(self, request, pk=None):
        """Routes ONGOING/COMPLETED/CANCELLED through the same Booking methods the driver
        portal's Start Trip/End Trip/Cancel actions use, instead of assigning status directly -
        otherwise an admin-driven transition would leave no trip_started_at/trip_ended_at trail,
        and would silently break the late-payment auto-complete safety net (which depends on
        trip_ended_at already being set - see Booking._complete_if_ended_and_paid)."""
        booking = self.get_object()
        new_status = request.data.get('status')
        if new_status not in BookingStatus.values:
            return Response(
                {'detail': f'Invalid status. Choose one of: {", ".join(BookingStatus.values)}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard: Cannot complete with outstanding balance - except a government contract, whose
        # balance stays outstanding until its invoice eventually clears (see
        # Booking._complete_if_ended_and_paid).
        if new_status == BookingStatus.COMPLETED and not booking.is_government_contract and booking.balance_due > 0:
            return Response(
                {'detail': f'Cannot complete trip. There is an outstanding balance of KES {booking.balance_due:,.2f}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Guard: cash was collected but not yet deposited into the Paybill - the customer has
        # paid, but SilverLake hasn't actually received the money yet (see Booking.has_undeposited_cash).
        if new_status == BookingStatus.COMPLETED and booking.has_undeposited_cash:
            return Response(
                {'detail': 'Cannot complete trip. Cash collected on this booking has not been deposited into the Paybill yet.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.core.exceptions import ValidationError as DjangoValidationError

        if new_status == BookingStatus.CANCELLED:
            # Staff can flag driver_at_fault - the driver went unavailable or delayed without
            # notice - to force a full refund even if the driver had already acknowledged the
            # trip (see Booking.mark_cancelled). Always staff-initiated here, so no extra
            # permission check is needed the way the customer-facing cancel action needs one.
            driver_at_fault = bool(request.data.get('driver_at_fault'))
            try:
                booking.mark_cancelled(driver_at_fault=driver_at_fault)
            except DjangoValidationError as exc:
                return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)
            return Response(BookingSerializer(booking).data)

        if new_status == BookingStatus.ONGOING:
            try:
                booking.start_trip()
            except DjangoValidationError as exc:
                return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)
            return Response(BookingSerializer(booking).data)

        if new_status == BookingStatus.COMPLETED:
            # balance_due <= 0 is already guaranteed by the guard above, so this always
            # actually completes it (assuming a valid CONFIRMED/ONGOING starting status) and
            # sends the same review-invite email end_trip() always sends on completion.
            try:
                booking.end_trip()
            except DjangoValidationError as exc:
                return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)
            return Response(BookingSerializer(booking).data)

        booking.status = new_status
        booking.save(update_fields=['status'])
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=['post'])
    def remind_balance(self, request, pk=None):
        """Nudges the assigned driver that this booking still has an outstanding balance -
        distinct from PaymentViewSet.remind, which is about a specific already-declared payment
        sitting unconfirmed. This covers a booking that's simply underpaid, whether or not the
        driver (or client) has declared anything yet. Any staff account can do this - it's just
        an email nudge, not a destructive or financial action."""
        from bookings.emails import send_booking_balance_reminder_email

        booking = self.get_object()
        if booking.status == BookingStatus.CANCELLED:
            return Response({'detail': 'This booking is cancelled.'}, status=status.HTTP_400_BAD_REQUEST)
        if not booking.driver_id:
            return Response({'detail': 'This booking has no driver assigned to remind.'}, status=status.HTTP_400_BAD_REQUEST)
        if booking.balance_due <= 0:
            return Response({'detail': 'This booking has no outstanding balance.'}, status=status.HTTP_400_BAD_REQUEST)
        if booking.last_balance_reminder_at and timezone.now() - booking.last_balance_reminder_at < BALANCE_REMINDER_COOLDOWN:
            return Response({'detail': 'A reminder was already sent recently. Please wait before sending another.'}, status=status.HTTP_400_BAD_REQUEST)

        booking.last_balance_reminder_at = timezone.now()
        booking.save(update_fields=['last_balance_reminder_at'])
        send_booking_balance_reminder_email(booking)
        log_admin_action(request, 'booking.remind_balance', booking)
        return Response(BookingSerializer(booking).data)

    @action(detail=False, methods=['post'], url_path='create-government')
    def create_government(self, request):
        """Creates a booking for a government contract - confirmed immediately, no deposit
        required, since payment for these arrives later via invoice rather than upfront like a
        normal customer booking (see Booking.is_government_contract). Staff-only: these are
        negotiated B2B arrangements, never something a customer sets up themselves. Reuses
        get_or_create_customer_account (the same helper the driver walk-in flow uses) since the
        department contact never registers or logs in - it's found/created by name/phone/email,
        not tied to whichever staff member happens to be creating this."""
        serializer = AdminGovernmentBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        organization = get_user_organization(request.user)
        if organization is not None and data['vehicle'].owner_id != organization.id:
            return Response({'detail': 'You can only book your own organization\'s vehicles.'}, status=status.HTTP_403_FORBIDDEN)

        customer, _ = get_or_create_customer_account(
            full_name=data['customer_name'], phone_number=data['customer_phone'], email=data['customer_email'],
        )

        booking = Booking(
            user=customer, vehicle=data['vehicle'], driver=data.get('driver'), service_type=data['service_type'],
            source=BookingSource.ADMIN, status=BookingStatus.CONFIRMED,
            is_government_contract=True, government_contract_reference=data['government_contract_reference'],
            customer_name=data['customer_name'], customer_phone=data['customer_phone'],
            customer_email=data['customer_email'], pickup_location=data['pickup_location'],
            dropoff_location=data['dropoff_location'], start_date=data['start_date'],
            end_date=data['end_date'], notes=data['notes'],
        )
        booking.save()
        booking.confirm_government_contract()
        log_admin_action(request, 'booking.create_government', booking, detail=data['government_contract_reference'])

        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='record-invoice-payment')
    def record_invoice_payment(self, request, pk=None):
        """Logs the real payment once a government department's invoice actually clears - weeks
        or months after the trip, unlike a normal customer's upfront M-Pesa/card/cash. No other
        side effects: the driver's payout already happened at trip completion (see
        Booking._ensure_driver_payout), this is purely a bookkeeping record so amount_paid/
        balance_due (and the receipt) reflect reality."""
        booking = self.get_object()
        if not booking.is_government_contract:
            return Response({'detail': 'This action is only for government-contract bookings.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = parse_amount(request.data.get('amount'))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if amount <= 0:
            return Response({'detail': 'Amount must be greater than zero.'}, status=status.HTTP_400_BAD_REQUEST)

        reference = request.data.get('reference', '').strip()
        Payment.objects.create(
            booking=booking, method=PaymentMethod.INVOICE, status=PaymentStatus.SUCCESSFUL,
            amount=amount, note=reference,
        )
        log_admin_action(request, 'booking.record_invoice_payment', booking, detail=f'KES {amount}')
        return Response(BookingSerializer(booking).data)


class AdminDriverPayoutViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-only view of what's owed to drivers. Everyone can see the ledger; only
    superadmins can actually mark a payout as disbursed, since that's real money moving."""

    queryset = DriverPayout.objects.all().select_related('driver', 'organization', 'booking').order_by('is_paid', '-created_at')
    serializer_class = AdminDriverPayoutSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        if organization is None:
            return self.queryset
        # A FleetPartner-owned vehicle's booking creates a DriverPayout with organization set
        # instead of driver (see Booking._ensure_driver_payout / _has_payout_recipient) - an
        # org's own staff see exactly their own payouts here, same shape as a driver-owned one.
        return self.queryset.filter(booking__vehicle__owner=organization)

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
        """Confirms a cash/card-sourced payout is legitimate, after reconciling with the driver
        or customer - requires a short note describing how it was reconciled, so verifying is an
        attested action with a trail, not just a button clicked on trust. Also requires every
        cash payment behind this booking to have a matching Paybill deposit logged (see
        payments.services.log_cash_deposit) - a driver can't get their payout verified while
        still holding onto (some of) the cash they collected."""
        note = request.data.get('note', '').strip()
        if not note:
            return Response(
                {'note': ['Describe how this was reconciled (e.g. "called customer, confirmed KES 5000").']},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payout = self.get_object()
        if payout.booking.has_undeposited_cash:
            return Response(
                {'detail': 'Every cash payment on this booking needs a matching Paybill deposit logged before this payout can be verified.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payout.verify(note)
        log_admin_action(request, 'payout.verify', payout, detail=note)
        return Response(AdminDriverPayoutSerializer(payout).data)


class AdminAuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only trail of who performed sensitive admin actions (role changes, suspensions,
    payouts, refunds). Viewing is not itself destructive, so any staff account can see it - an
    org-scoped account only sees entries that resolved to their own organization (see
    core.audit._infer_organization); a genuine SilverLake staff/superadmin sees everything,
    including entries with no derivable organization at all (driver suspensions, announcements,
    fleet-type/taxonomy changes, driver applications - none of these belong to any one
    partner's fleet)."""

    queryset = AuditLog.objects.all().select_related('actor', 'organization')
    serializer_class = AdminAuditLogSerializer
    permission_classes = [IsSupportStaff]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        if organization is None:
            return self.queryset
        return self.queryset.filter(organization=organization)


class AdminRefundViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-only view of refunds owed after a cancelled booking. Everyone can see the ledger;
    only superadmins can mark one issued, since that's real money moving."""

    queryset = Refund.objects.all().select_related('booking').order_by('status', '-created_at')
    serializer_class = AdminRefundSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        if organization is None:
            return self.queryset
        return self.queryset.filter(booking__vehicle__owner=organization)

    @action(detail=True, methods=['post'], url_path='mark-issued')
    def mark_issued(self, request, pk=None):
        refund = self.get_object()
        refund.mark_issued(reference=request.data.get('reference', ''))
        log_admin_action(request, 'refund.mark_issued', refund, detail=request.data.get('reference', ''))
        return Response(AdminRefundSerializer(refund).data)


class AdminFleetPartnerViewSet(viewsets.ModelViewSet):
    """Superadmin-only management of registered fleet-owning companies (see FleetPartner) -
    holds their own Paybill credentials and platform fee rate, so every action here is
    financial/fleet-composition-adjacent, unlike most other admin viewsets which open list/view
    to support staff. Deleting one a vehicle still references is blocked (Vehicle.owner is
    PROTECT) rather than silently orphaning that vehicle's ownership."""

    queryset = FleetPartner.objects.all()
    serializer_class = AdminFleetPartnerSerializer
    permission_classes = [IsPlatformSuperAdmin]

    def perform_create(self, serializer):
        partner = serializer.save()
        log_admin_action(self.request, 'fleet_partner.create', partner)
        if partner.contact_email:
            # Their first org-admin account, scoped to just this organization - see
            # core.services.invite_staff_account for why this emails a "set your password" link
            # rather than a raw password. No-ops (silently) if contact_email wasn't given at
            # registration - use the invite_admin action below once it's added.
            from .services import invite_staff_account

            invite_staff_account(partner.contact_email, organization=partner, is_superuser=True)

    def perform_update(self, serializer):
        partner = serializer.save()
        log_admin_action(self.request, 'fleet_partner.update', partner)

    @action(detail=True, methods=['post'], url_path='invite-admin')
    def invite_admin(self, request, pk=None):
        """Sends (or re-sends) this partner's org-admin invite - for when contact_email wasn't
        set at registration, or the original invite needs resending."""
        from .services import invite_staff_account

        partner = self.get_object()
        if not partner.contact_email:
            return Response(
                {'detail': 'This partner has no contact email on file to send an invite to.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invite_staff_account(partner.contact_email, organization=partner, is_superuser=True)
        log_admin_action(request, 'fleet_partner.invite_admin', partner)
        return Response(AdminFleetPartnerSerializer(partner).data)

    @action(detail=True, methods=['post'])
    def notify(self, request, pk=None):
        """Lets a genuine SilverLake superadmin send a one-off in-app message straight to this
        organization's own admin(s) - the manual counterpart to every other automatic event in
        the notifications app. Platform-superadmin-only (see this ViewSet's own
        permission_classes) since it's a direct line to one specific partner, not a broadcast a
        partner's own org-admin could send to themselves."""
        partner = self.get_object()
        message = request.data.get('message', '').strip()
        if not message:
            return Response({'message': ['A message is required.']}, status=status.HTTP_400_BAD_REQUEST)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(NotificationEvent.ADMIN_MESSAGE, message, organization=partner, link_path='/admin')
        log_admin_action(request, 'fleet_partner.notify', partner, detail=message)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def destroy(self, request, *args, **kwargs):
        return _delete_or_block(
            request, self.get_object(), 'fleet_partner.delete',
            'This partner still owns a vehicle - reassign it before deleting the partner.',
        )


class AdminVehicleCategoryViewSet(viewsets.ModelViewSet):
    """Staff-only management of fleet types (e.g. "Executive SUV") - these used to be a fixed
    enum in code, now a plain admin-editable list. Deleting one a vehicle/submission/driver
    application still references is blocked rather than silently orphaning those records."""

    queryset = VehicleCategory.objects.all().order_by('order', 'name')
    serializer_class = VehicleCategorySerializer

    def get_permissions(self):
        # Shared platform-wide taxonomy - readable by any staff (including a FleetPartner's own
        # org staff, who need it to populate their own vehicle forms), but mutating it is
        # SilverLake-only, not delegated to any single partner even at the superadmin tier.
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsPlatformSuperAdmin()]
        return [IsSupportStaff()]

    def perform_create(self, serializer):
        category = serializer.save()
        log_admin_action(self.request, 'vehicle_category.create', category)

    def perform_update(self, serializer):
        category = serializer.save()
        log_admin_action(self.request, 'vehicle_category.update', category)

    def destroy(self, request, *args, **kwargs):
        return _delete_or_block(
            request, self.get_object(), 'vehicle_category.delete',
            'This fleet type is still assigned to a vehicle, submission, or driver application and cannot be deleted.',
        )


class AdminFleetViewSet(viewsets.ModelViewSet):
    """Staff-only full CRUD for Vehicle records, plus toggle availability.

    Create/update/delete (fleet composition and pricing) are superadmin-only; support
    staff can list/view/toggle availability."""

    queryset = Vehicle.objects.all().select_related('category', 'driver').prefetch_related('service_records').order_by('name')
    serializer_class = AdminVehicleSerializer

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        queryset = self.queryset if organization is None else self.queryset.filter(owner=organization)

        params = self.request.query_params
        queryset = search_filter(queryset, params.get('search', '').strip(), ['name', 'tagline'])
        category = params.get('category', '').strip()
        if category:
            queryset = queryset.filter(category__slug=category)
        is_available = params.get('is_available', '').strip()
        if is_available in ('true', 'false'):
            queryset = queryset.filter(is_available=(is_available == 'true'))
        return queryset

    def perform_create(self, serializer):
        organization = get_user_organization(self.request.user)
        if organization is not None:
            # An org-admin can only ever add a vehicle to their own organization's fleet - never
            # SilverLake's own, never a different partner's, regardless of what was submitted.
            vehicle = serializer.save(owner=organization, is_company_owned=False)
        else:
            vehicle = serializer.save()
        log_admin_action(self.request, 'vehicle.create', vehicle)

    def perform_update(self, serializer):
        old_files = capture_replaced_files(serializer, ['image', 'insurance_document'])
        organization = get_user_organization(self.request.user)
        if organization is not None:
            # Can't reassign their own vehicle away to a different organization or flip it to
            # company-owned - get_queryset() already stops them reaching a vehicle they don't
            # own, this stops them editing one they do own out of their own scope.
            vehicle = serializer.save(owner=organization, is_company_owned=False)
        else:
            vehicle = serializer.save()
        delete_files(old_files)
        log_admin_action(self.request, 'vehicle.update', vehicle)

    def destroy(self, request, *args, **kwargs):
        return _delete_or_block(
            request, self.get_object(), 'vehicle.delete',
            'This vehicle has bookings on file and cannot be deleted. Mark it unavailable instead.',
        )

    @action(detail=True, methods=['post'], url_path='toggle-availability')
    def toggle_availability(self, request, pk=None):
        vehicle = self.get_object()
        vehicle.is_available = not vehicle.is_available
        vehicle.save(update_fields=['is_available'])
        return Response(AdminVehicleSerializer(vehicle).data)

    @action(detail=True, methods=['post'], url_path='gallery')
    def add_gallery_images(self, request, pk=None):
        """Adds one or more gallery photos to a company-created vehicle - a driver's own
        submission already requires 2+ photos at submission time, but an admin-created vehicle
        previously had no way to add anything beyond its single cover image."""
        vehicle = self.get_object()
        images = request.FILES.getlist('images')
        if not images:
            return Response({'detail': 'At least one image is required.'}, status=status.HTTP_400_BAD_REQUEST)
        created = [VehicleImage.objects.create(vehicle=vehicle, image=image) for image in images]
        log_admin_action(request, 'vehicle.add_gallery_images', vehicle, detail=f'{len(created)} photo(s)')
        return Response(VehicleImageSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'gallery/(?P<image_id>\d+)')
    def remove_gallery_image(self, request, pk=None, image_id=None):
        vehicle = self.get_object()
        image = get_object_or_404(VehicleImage, pk=image_id, vehicle=vehicle)
        log_admin_action(request, 'vehicle.remove_gallery_image', vehicle)
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='service-records')
    def add_service_record(self, request, pk=None):
        """Lets admin log a service/maintenance event directly - mainly for company-owned
        vehicles, which have no owning driver-partner to log one themselves from the portal."""
        vehicle = self.get_object()
        serializer = VehicleServiceRecordSerializer(data={**request.data, 'vehicle': vehicle.id})
        serializer.is_valid(raise_exception=True)
        record = serializer.save()
        log_admin_action(request, 'vehicle.add_service_record', vehicle, detail=record.notes)
        return Response(VehicleServiceRecordSerializer(record).data, status=status.HTTP_201_CREATED)


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

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        if organization is None:
            return self.queryset
        # Free-form testimonials with no booking (booking is nullable) aren't tied to any
        # vehicle/org, so they're correctly excluded here, not just the ones for other orgs.
        return self.queryset.filter(booking__vehicle__owner=organization)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        review = self.get_object()
        review.is_approved = True
        review.save(update_fields=['is_approved'])
        if review.driver_id:
            review.driver.recalculate_rating()
        log_admin_action(request, 'review.approve', review)
        return Response(AdminReviewSerializer(review).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject = mark unapproved (keep record but hide from public)."""
        review = self.get_object()
        review.is_approved = False
        review.save(update_fields=['is_approved'])
        if review.driver_id:
            review.driver.recalculate_rating()
        log_admin_action(request, 'review.reject', review)
        return Response(AdminReviewSerializer(review).data)

    def perform_destroy(self, instance):
        driver = instance.driver
        log_admin_action(self.request, 'review.delete', instance)
        instance.delete()
        if driver:
            driver.recalculate_rating()
