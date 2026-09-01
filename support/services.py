"""Support-side background sweep helpers - see payments.scheduler for how these get wired into
the project's single in-process scheduler."""
from datetime import timedelta

from django.utils import timezone

from .models import SupportTicket, TicketStatus

# How long a ticket can sit OPEN - nobody's even moved it to in_progress - before staff get an
# automated nudge. Long enough that normal business-hours turnaround isn't treated as a
# problem, short enough that a customer complaint doesn't sit for days unaddressed.
TICKET_ESCALATION_GRACE_PERIOD = timedelta(hours=48)
# Distinct from a one-shot flag - a ticket still stuck the next day deserves resurfacing, not
# just flagged once and forgotten. Shorter than the payout/corporate-invoice cooldowns
# elsewhere in this app, since this is customer-facing responsiveness, not internal
# bookkeeping - it should stay visible daily, not weekly.
TICKET_ESCALATION_COOLDOWN = timedelta(hours=24)


def escalate_stale_support_tickets():
    """Runs on every scheduler tick (see payments.scheduler). SUPPORT_TICKET_CREATED already
    alerts staff the moment a ticket is filed, but until this, nothing ever followed up if it
    then just sat there - a ticket could stay OPEN, with nobody having even started on it, for
    as long as nobody happened to notice it in the queue.

    Anchored on updated_at, not created_at - a customer reopening a resolved ticket (see
    SupportTicket.reopen) bumps updated_at back to now, so the clock correctly restarts for
    what is, in effect, a fresh unresolved issue again. Scoped to status=OPEN only: once staff
    move a ticket to in_progress, someone is at least actively on it, so this stops watching it
    - a stalled in_progress ticket is a different, harder judgment call this sweep doesn't try
    to make."""
    from notifications.models import NotificationEvent
    from notifications.services import notify

    from .emails import send_support_ticket_stale_staff_notification_email

    now = timezone.now()
    cutoff = now - TICKET_ESCALATION_GRACE_PERIOD

    candidates = SupportTicket.objects.filter(status=TicketStatus.OPEN, updated_at__lt=cutoff).select_related('user')

    for ticket in candidates:
        if ticket.escalation_reminded_at and now - ticket.escalation_reminded_at < TICKET_ESCALATION_COOLDOWN:
            continue
        ticket.escalation_reminded_at = now
        ticket.save(update_fields=['escalation_reminded_at'])
        send_support_ticket_stale_staff_notification_email(ticket)
        notify(
            NotificationEvent.SUPPORT_TICKET_STALE,
            f'Ticket #{ticket.pk} "{ticket.subject}" has sat open for over '
            f'{int(TICKET_ESCALATION_GRACE_PERIOD.total_seconds() // 3600)}h with no response',
            link_path='/admin/support',
        )
