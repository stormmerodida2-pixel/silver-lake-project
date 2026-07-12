from django.core.management.base import BaseCommand

from payments.services import expire_stale_mpesa_payments


class Command(BaseCommand):
    help = (
        "Marks PENDING M-Pesa payments older than STALE_MPESA_PENDING_THRESHOLD as FAILED. "
        "There's no Safaricom Transaction Status Query integration to actually ask whether one "
        "of these went through (this project has no Initiator credentials for that API yet), "
        "but a real STK Push resolves within seconds of the customer acting on their phone, so "
        "one still PENDING this long is practically certain to have been abandoned rather than "
        "genuinely still in flight. This now also runs automatically every few minutes via an "
        "in-process background thread (see payments.scheduler, started from AppConfig.ready) - "
        "running this command by hand is only needed for an immediate one-off sweep."
    )

    def handle(self, *args, **options):
        count = expire_stale_mpesa_payments()
        self.stdout.write(self.style.SUCCESS(f'Marked {count} stale pending M-Pesa payment(s) as failed.'))
