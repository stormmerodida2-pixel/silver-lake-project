from rest_framework import generics, mixins, permissions, response, serializers, viewsets
from rest_framework.throttling import ScopedRateThrottle

from fleet.models import VehicleServiceRecord, VehicleSubmission
from fleet.serializers import VehicleServiceRecordSerializer

from .emails import (
    send_driver_away_notification,
    send_new_driver_application_notification,
    send_new_vehicle_submission_notification,
)
from .models import Driver, DriverApplication
from .permissions import IsDriverUser
from .serializers import (
    DriverApplicationSerializer,
    DriverAwaySerializer,
    DriverPortalSerializer,
    DriverSerializer,
    VehicleSubmissionSerializer,
)


class DriverViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Driver.objects.filter(is_active=True)
    serializer_class = DriverSerializer


class DriverApplicationCreateView(generics.CreateAPIView):
    """Public 'become a driver' submission - stays pending until an admin approves it.

    Unauthenticated and accepts file uploads (license photo, logbook), so it's throttled
    like the other public write endpoints (registration, password reset) to stop it being
    used to spam the review queue or disk with junk submissions."""

    queryset = DriverApplication.objects.all()
    serializer_class = DriverApplicationSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'driver-application'

    def perform_create(self, serializer):
        application = serializer.save()
        send_new_driver_application_notification(application)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.DRIVER_APPLICATION, f'New driver application from {application.full_name}',
            link_path='/admin/drivers',
        )


class DriverMeView(generics.RetrieveAPIView):
    """The logged-in driver's own portal profile: contact info, live vehicles, submissions."""

    serializer_class = DriverPortalSerializer
    permission_classes = [IsDriverUser]

    def get_object(self):
        return self.request.user.driver_profile


class DriverAwayView(generics.UpdateAPIView):
    """Lets a driver mark themselves away/available with a reason, visible only to admins."""

    serializer_class = DriverAwaySerializer
    permission_classes = [IsDriverUser]
    http_method_names = ['patch']

    def get_object(self):
        return self.request.user.driver_profile

    def update(self, request, *args, **kwargs):
        driver = self.get_object()
        was_away = driver.is_away
        super().update(request, *args, **kwargs)
        driver.refresh_from_db()
        if driver.is_away and not was_away:
            send_driver_away_notification(driver)

            from notifications.models import NotificationEvent
            from notifications.services import notify

            notify(NotificationEvent.DRIVER_AWAY, f'{driver.full_name} marked themselves away', link_path='/admin/drivers')
        return response.Response(DriverPortalSerializer(driver).data)


class DriverVehicleSubmissionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """A driver's own submitted-for-review vehicles. Approval (which creates the live
    Vehicle) is handled on the admin side."""

    serializer_class = VehicleSubmissionSerializer
    permission_classes = [IsDriverUser]

    def get_queryset(self):
        return VehicleSubmission.objects.filter(
            driver=self.request.user.driver_profile,
        ).select_related('category')

    def perform_create(self, serializer):
        submission = serializer.save(driver=self.request.user.driver_profile)
        send_new_vehicle_submission_notification(submission)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.VEHICLE_SUBMISSION, f'{submission.driver.full_name} submitted a vehicle for review',
            link_path='/admin/drivers',
        )


class DriverVehicleServiceRecordViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """A driver-partner's own service/maintenance log for their own vehicle(s) - gives admins a
    shared record of what's been done on a car without anyone having to ask. Scoped to vehicles
    this driver actually owns; company-owned fleet vehicles (no owning driver) are logged by
    admin instead, from the Fleet page."""

    serializer_class = VehicleServiceRecordSerializer
    permission_classes = [IsDriverUser]

    def get_queryset(self):
        return VehicleServiceRecord.objects.filter(
            vehicle__driver=self.request.user.driver_profile,
        ).select_related('vehicle')

    def perform_create(self, serializer):
        vehicle = serializer.validated_data.get('vehicle')
        driver = self.request.user.driver_profile
        if not vehicle or vehicle.driver_id != driver.id:
            raise serializers.ValidationError({'vehicle': 'You can only log a service for your own vehicle.'})
        serializer.save(logged_by=driver)
