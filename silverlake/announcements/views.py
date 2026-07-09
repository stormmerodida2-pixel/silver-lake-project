from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import log_admin_action
from core.permissions import IsSuperAdmin

from .models import Announcement, AnnouncementAudience
from .serializers import AdminAnnouncementSerializer, MyAnnouncementSerializer


def _audiences_for(user):
    """Which audiences this user belongs to - a plain customer only ever matches 'clients',
    but a staff member or driver-partner can match more than one (e.g. a staff member who's
    also booked a car themselves)."""
    audiences = [AnnouncementAudience.CLIENTS]
    if user.is_staff:
        audiences.append(AnnouncementAudience.STAFF)
    driver = getattr(user, 'driver_profile', None)
    if driver and driver.is_active:
        audiences.append(AnnouncementAudience.DRIVERS)
    return audiences


class AdminAnnouncementViewSet(viewsets.ModelViewSet):
    """Superadmin-only - broadcasting to a whole audience is significant enough that it
    shouldn't be a day-to-day support-staff action."""

    queryset = Announcement.objects.all().select_related('created_by')
    serializer_class = AdminAnnouncementSerializer
    permission_classes = [IsSuperAdmin]

    def perform_create(self, serializer):
        announcement = serializer.save(created_by=self.request.user)
        log_admin_action(self.request, 'announcement.create', announcement, detail=announcement.audience)

    def perform_update(self, serializer):
        announcement = serializer.save()
        log_admin_action(self.request, 'announcement.update', announcement)

    def perform_destroy(self, instance):
        log_admin_action(self.request, 'announcement.delete', instance)
        instance.delete()


class MyAnnouncementsView(generics.ListAPIView):
    """Active announcements aimed at any audience the current user belongs to."""

    serializer_class = MyAnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Announcement.objects.filter(
            is_active=True, audience__in=_audiences_for(self.request.user),
        ).prefetch_related('read_by')


class MarkAnnouncementReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        announcement = get_object_or_404(
            Announcement, pk=pk, is_active=True, audience__in=_audiences_for(request.user),
        )
        announcement.read_by.add(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
