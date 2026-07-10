from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import log_admin_action
from core.permissions import IsSuperAdmin, IsSupportStaff

from .models import Announcement, AnnouncementAudience, AnnouncementStatus
from .serializers import AdminAnnouncementSerializer, MyAnnouncementSerializer

# Not expired = no expires_at at all, or one that hasn't passed yet.
_NOT_EXPIRED = Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())


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


# Actions that broadcast directly, change what's already live, or destroy a record -
# superadmin-only. 'create'/'list'/'retrieve' are open to support staff too (scoped below).
SUPERADMIN_ONLY_ACTIONS = {'update', 'partial_update', 'destroy', 'approve', 'reject'}


class AdminAnnouncementViewSet(viewsets.ModelViewSet):
    """A superadmin can broadcast to any audience directly, no review needed. Support staff
    can only propose client-facing announcements - each proposal starts out pending and
    invisible until a superadmin approves or rejects it (see perform_create/approve/reject)."""

    serializer_class = AdminAnnouncementSerializer

    def get_queryset(self):
        queryset = Announcement.objects.all().select_related('created_by', 'reviewed_by')
        if self.request.user.is_superuser:
            return queryset
        # Support staff only ever manage their own proposals, not the full broadcast history.
        return queryset.filter(created_by=self.request.user)

    def get_permissions(self):
        if self.action in SUPERADMIN_ONLY_ACTIONS:
            return [IsSuperAdmin()]
        return [IsSupportStaff()]

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_superuser:
            announcement = serializer.save(created_by=user)
        else:
            # Force these regardless of what was submitted - a support-staff proposal is always
            # client-facing and always starts pending, never live until a superadmin signs off.
            announcement = serializer.save(
                created_by=user, audience=AnnouncementAudience.CLIENTS,
                status=AnnouncementStatus.PENDING, is_active=False,
            )
        log_admin_action(self.request, 'announcement.create', announcement, detail=announcement.audience)

    def perform_update(self, serializer):
        announcement = serializer.save()
        log_admin_action(self.request, 'announcement.update', announcement)

    def perform_destroy(self, instance):
        log_admin_action(self.request, 'announcement.delete', instance)
        instance.delete()

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        announcement = self.get_object()
        announcement.status = AnnouncementStatus.APPROVED
        announcement.is_active = True
        announcement.reviewed_by = request.user
        announcement.review_note = ''
        announcement.save(update_fields=['status', 'is_active', 'reviewed_by', 'review_note'])
        log_admin_action(self.request, 'announcement.approve', announcement)
        return Response(self.get_serializer(announcement).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        announcement = self.get_object()
        announcement.status = AnnouncementStatus.REJECTED
        announcement.is_active = False
        announcement.reviewed_by = request.user
        announcement.review_note = request.data.get('review_note', '')
        announcement.save(update_fields=['status', 'is_active', 'reviewed_by', 'review_note'])
        log_admin_action(self.request, 'announcement.reject', announcement, detail=announcement.review_note)
        return Response(self.get_serializer(announcement).data)


class MyAnnouncementsView(generics.ListAPIView):
    """Active, approved announcements aimed at any audience the current user belongs to."""

    serializer_class = MyAnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Announcement.objects.filter(
            _NOT_EXPIRED, is_active=True, status=AnnouncementStatus.APPROVED,
            audience__in=_audiences_for(self.request.user),
        ).prefetch_related('read_by')


class MarkAnnouncementReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        announcement = get_object_or_404(
            Announcement.objects.filter(_NOT_EXPIRED), pk=pk, is_active=True, status=AnnouncementStatus.APPROVED,
            audience__in=_audiences_for(request.user),
        )
        announcement.read_by.add(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
