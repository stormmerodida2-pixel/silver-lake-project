from rest_framework import generics, mixins, permissions, response, viewsets

from fleet.models import VehicleSubmission

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
    """Public 'become a driver' submission - stays pending until an admin approves it."""

    queryset = DriverApplication.objects.all()
    serializer_class = DriverApplicationSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        application = serializer.save()
        send_new_driver_application_notification(application)


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
        return response.Response(DriverPortalSerializer(driver).data)


class DriverVehicleSubmissionViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """A driver's own submitted-for-review vehicles. Approval (which creates the live
    Vehicle) is handled on the admin side."""

    serializer_class = VehicleSubmissionSerializer
    permission_classes = [IsDriverUser]

    def get_queryset(self):
        return VehicleSubmission.objects.filter(driver=self.request.user.driver_profile)

    def perform_create(self, serializer):
        submission = serializer.save(driver=self.request.user.driver_profile)
        send_new_vehicle_submission_notification(submission)
