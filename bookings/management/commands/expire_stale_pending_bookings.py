from django.core.management.base import BaseCommand

from bookings.services import expire_stale_pending_bookings


class Command(BaseCommand):
    help = (
        "Auto-cancels a PENDING booking that's had zero payment activity for "
        "STALE_PENDING_BOOKING_THRESHOLD (24 hours) - otherwise an abandoned checkout blocks "
        "the vehicle from public visibility and from being booked by anyone else indefinitely. "
        "This now also runs automatically every few minutes via an in-process background "
        "thread (see payments.scheduler, started from AppConfig.ready) - running this command "
        "by hand is only needed for an immediate one-off sweep."
    )

    def handle(self, *args, **options):
        count = expire_stale_pending_bookings()
        self.stdout.write(self.style.SUCCESS(f'Auto-cancelled {count} stale unpaid pending booking(s).'))
