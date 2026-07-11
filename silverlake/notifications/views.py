from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsSupportStaff, get_user_organization
from drivers.permissions import IsDriverUser

from .models import Notification, NotificationEvent, NotificationPreference
from .serializers import NotificationSerializer


class _NotificationReadStateMixin:
    """Shared read-state actions (mark-read/mark-all-read/unread-count) and mute preferences for
    any notification feed - only get_queryset differs between the admin dashboard's, the driver
    portal's, and a client's own."""

    def _exclude_muted(self, queryset):
        muted = NotificationPreference.objects.filter(user=self.request.user).values_list('event', flat=True)
        return queryset.exclude(event__in=muted)

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

    @action(detail=False, methods=['get'])
    def preferences(self, request):
        """Which event types (from NotificationEvent, not just the ones this particular feed
        happens to use) the requesting user has muted - shared across all three feeds since it's
        the same account's own preference regardless of which bell they're looking at."""
        muted = list(NotificationPreference.objects.filter(user=request.user).values_list('event', flat=True))
        return Response({'muted_events': muted})

    @action(detail=False, methods=['post'])
    def mute(self, request):
        event = request.data.get('event')
        if event not in NotificationEvent.values:
            return Response({'event': ['Not a valid event.']}, status=status.HTTP_400_BAD_REQUEST)
        NotificationPreference.objects.get_or_create(user=request.user, event=event)
        return Response(status=204)

    @action(detail=False, methods=['post'])
    def unmute(self, request):
        event = request.data.get('event')
        NotificationPreference.objects.filter(user=request.user, event=event).delete()
        return Response(status=204)


class NotificationViewSet(_NotificationReadStateMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
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
        return self._exclude_muted(queryset).prefetch_related('read_by')


class DriverNotificationViewSet(_NotificationReadStateMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """The driver portal's in-app event feed - being booked by a client, a cancelled trip,
    payment/cash-deposit reminders, a payout being paid, and a submitted vehicle being
    approved/rejected. Scoped to exactly the requesting driver's own notifications, never
    another driver's."""

    serializer_class = NotificationSerializer
    permission_classes = [IsDriverUser]

    def get_queryset(self):
        queryset = Notification.objects.filter(driver=self.request.user.driver_profile)
        return self._exclude_muted(queryset).prefetch_related('read_by')


class ClientNotificationViewSet(_NotificationReadStateMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """A logged-in customer's own in-app event feed - booking confirmed, a cancelled booking, a
    cash/card payment recorded, a trip completed (review invite), and a refund issued. Scoped to
    exactly the requesting account, never another customer's - any authenticated user can read
    their own, the same as any other self-service account page."""

    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Notification.objects.filter(user=self.request.user)
        return self._exclude_muted(queryset).prefetch_related('read_by')
