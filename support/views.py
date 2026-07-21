from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import IsPlatformStaff

from .models import SupportTicket, SupportTicketPhoto, TicketStatus
from .serializers import AdminSupportTicketSerializer, SupportTicketSerializer


class MySupportTicketViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet,
):
    """A customer's own support tickets - filed from their own account, not the existing
    no-login cash-payment-dispute link. No update/destroy: once filed, a customer can only
    reopen a resolved ticket (see reopen()), never edit or delete what they originally wrote."""

    serializer_class = SupportTicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SupportTicket.objects.filter(user=self.request.user).select_related('booking__vehicle')

    def perform_create(self, serializer):
        ticket = serializer.save(user=self.request.user)
        for image in self.request.FILES.getlist('photos'):
            SupportTicketPhoto.objects.create(ticket=ticket, image=image)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.SUPPORT_TICKET_CREATED,
            f'{ticket.user.get_full_name() or ticket.user.email} filed a support ticket: {ticket.subject}',
            link_path='/admin/support',
        )

        from .emails import send_support_ticket_created_staff_notification_email

        send_support_ticket_created_staff_notification_email(ticket)

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        ticket = self.get_object()
        if ticket.status != TicketStatus.RESOLVED:
            return Response({'detail': 'Only a resolved ticket can be reopened.'}, status=status.HTTP_400_BAD_REQUEST)
        ticket.reopen()

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.SUPPORT_TICKET_CREATED,
            f'{ticket.user.get_full_name() or ticket.user.email} reopened ticket #{ticket.pk}: {ticket.subject}',
            link_path='/admin/support',
        )

        return Response(SupportTicketSerializer(ticket, context={'request': request}).data)


class AdminSupportTicketViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-side ticket queue - platform-staff-only (see SupportTicket's own docstring for why),
    day-to-day operational tier like reviews/announcement moderation."""

    serializer_class = AdminSupportTicketSerializer
    permission_classes = [IsPlatformStaff]
    queryset = SupportTicket.objects.all().select_related('user', 'booking__vehicle', 'resolved_by')

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """Moves a ticket to in_progress or resolved (the latter requiring a resolution_note) -
        one action for both, mirroring AdminBookingViewSet.set_status's own
        single-action-for-multiple-transitions shape. Either transition notifies the customer
        (in-app + email) - previously only resolving one did, leaving the customer with no
        signal at all that their ticket was even being looked at in the meantime."""
        ticket = self.get_object()
        new_status = request.data.get('status')
        if new_status not in (TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED):
            return Response(
                {'detail': f'status must be one of: {TicketStatus.IN_PROGRESS}, {TicketStatus.RESOLVED}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        note = request.data.get('resolution_note', '').strip()
        if new_status == TicketStatus.RESOLVED and not note:
            return Response(
                {'detail': 'Describe how this ticket was resolved.'}, status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.status = new_status
        update_fields = ['status', 'updated_at']
        if new_status == TicketStatus.RESOLVED:
            from django.utils import timezone

            ticket.resolution_note = note
            ticket.resolved_at = timezone.now()
            ticket.resolved_by = request.user
            update_fields += ['resolution_note', 'resolved_at', 'resolved_by']
        ticket.save(update_fields=update_fields)

        from core.audit import log_admin_action

        log_admin_action(request, 'supportticket.respond', ticket, detail=new_status)

        if new_status == TicketStatus.IN_PROGRESS:
            from notifications.models import NotificationEvent
            from notifications.services import notify

            notify(
                NotificationEvent.SUPPORT_TICKET_IN_PROGRESS,
                f'Your support ticket "{ticket.subject}" is being looked into',
                user=ticket.user, link_path='/account/support',
            )

            from .emails import send_support_ticket_in_progress_email

            send_support_ticket_in_progress_email(ticket)

        if new_status == TicketStatus.RESOLVED:
            from notifications.models import NotificationEvent
            from notifications.services import notify

            notify(
                NotificationEvent.SUPPORT_TICKET_RESOLVED,
                f'Your support ticket "{ticket.subject}" has been resolved',
                user=ticket.user, link_path='/account/support',
            )

            from .emails import send_support_ticket_resolved_email

            send_support_ticket_resolved_email(ticket)

        return Response(AdminSupportTicketSerializer(ticket, context={'request': request}).data)
