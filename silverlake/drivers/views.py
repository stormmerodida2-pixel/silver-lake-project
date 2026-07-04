from rest_framework import generics, permissions, viewsets

from .emails import send_new_driver_application_notification
from .models import Driver, DriverApplication
from .serializers import DriverApplicationSerializer, DriverSerializer


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
