from django.core.management.base import BaseCommand
from django.utils import timezone

from payments.models import Payment, PaymentMethod, PaymentStatus
from payments.services import STALE_MPESA_PENDING_THRESHOLD


class Command(BaseCommand):
    help = (
        "Marks PENDING M-Pesa payments older than STALE_MPESA_PENDING_THRESHOLD as FAILED. "
        "There's no Safaricom Transaction Status Query integration to actually ask whether one "
        "of these went through (this project has no Initiator credentials for that API yet) - "
        "but a real STK Push resolves within seconds of the customer acting on their phone, so "
        "one still PENDING this long is practically certain to have been abandoned rather than "
        "genuinely still in flight. Intended to run periodically (e.g. a cron job or Windows "
        "Task Scheduler entry), since this project has no background task runner of its own."
    )

    def handle(self, *args, **options):
        cutoff = timezone.now() - STALE_MPESA_PENDING_THRESHOLD
        stale = Payment.objects.filter(
            method=PaymentMethod.MPESA, status=PaymentStatus.PENDING, created_at__lt=cutoff,
        )
        count = stale.update(status=PaymentStatus.FAILED)
        self.stdout.write(self.style.SUCCESS(f'Marked {count} stale pending M-Pesa payment(s) as failed.'))
