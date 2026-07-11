from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsSupportStaff, get_user_organization

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The admin dashboard's in-app event feed - read-only (nothing creates one directly through
    the API; see notifications.services.notify, called from the events themselves) plus the
    read-state actions the notification bell needs. Any staff account can read/mark-read - this
    is informational, not a financial or destructive action, so there's no superadmin-only tier
    the way payouts/refunds have."""

    serializer_class = NotificationSerializer
    permission_classes = [IsSupportStaff]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        queryset = Notification.objects.all() if organization is None else Notification.objects.filter(organization=organization)
        return queryset.prefetch_related('read_by')

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.read_by.add(request.user)
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        for notification in self.get_queryset().exclude(read_by=request.user):
            notification.read_by.add(request.user)
        return Response(status=204)

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = self.get_queryset().exclude(read_by=request.user).count()
        return Response({'count': count})
