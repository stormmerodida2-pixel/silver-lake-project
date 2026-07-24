"""In-process background scheduler for periodic cleanup tasks. This project has no Celery/cron
of its own, so rather than requiring someone to configure an external OS-level Task Scheduler or
cron entry, a lightweight daemon thread does it automatically for as long as the Django process
is alive. Runs five independent sweeps on the same interval:
payments.services.expire_stale_mpesa_payments (abandoned STK pushes),
payments.services.remind_undeposited_cash (nudging a driver to deposit collected cash, starting
soon after they confirm receiving it - independent of the booking's own end date),
payments.services.escalate_stuck_bookings (auto-reminding, then escalating to staff, a booking
whose payment/deposit has sat unresolved past its scheduled end date),
bookings.services.escalate_unacknowledged_bookings (alerting staff once an online booking's
driver hasn't acknowledged it within its deadline), and
bookings.services.expire_stale_pending_bookings (auto-cancelling a PENDING booking that's had
zero payment activity for a full day, so an abandoned checkout doesn't block a vehicle from
public visibility or from being booked by someone else indefinitely).

Deliberately not started for management commands (manage.py test/migrate/shell/etc.) - none of
those keep a process running long enough for this to matter, and starting it during `test` in
particular would let a stray background thread touch the test database. Only starts under the
actual long-lived server process (runserver's real worker, or a production WSGI/ASGI process) -
see _should_run().

If this later moves to a multi-process production server (gunicorn with several workers, say),
each worker starts its own copy - slightly redundant (every sweep runs more than once per
interval), but harmless: expire_stale_mpesa_payments is an idempotent UPDATE query, and the two
escalation sweeps guard every action behind a cooldown/one-time field.
"""
import logging
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 300

# Set at the start of every sweep iteration - lets core.views' health check report whether this
# thread is actually alive and ticking on schedule, not just that .start() was once called.
last_tick_at = None

# manage.py subcommands that never serve requests long enough for a background sweep to make
# sense - and in the case of `test`, one we specifically must not touch the test database from.
_NON_SERVING_COMMANDS = {
    'test', 'migrate', 'makemigrations', 'shell', 'shell_plus', 'collectstatic',
    'createsuperuser', 'dbshell', 'showmigrations', 'check', 'dumpdata', 'loaddata',
}

_started = False


def _should_run():
    argv = sys.argv
    if len(argv) > 1:
        command = argv[1]
        if command in _NON_SERVING_COMMANDS:
            return False
        if command == 'runserver':
            # Django's autoreloader re-imports every app twice - once for the watcher process,
            # again for the actual worker - RUN_MAIN is only set in the latter.
            return os.environ.get('RUN_MAIN') == 'true'
    return True


def _record_sweep_failure(label):
    """logger.exception() alone only ever reaches `docker logs` - nothing surfaces a background
    sweep failure anywhere a superadmin would actually see it, unlike a frontend crash or a
    failed API call (see core.models.ClientErrorReport). Persisting one here means System
    Health's error table is genuinely "any error", not just the user-facing half. Imported
    lazily, matching this module's existing lazy cross-app imports inside _sweep_loop."""
    logger.exception(label)
    from core.models import ClientErrorReport

    ClientErrorReport.objects.create(
        source=ClientErrorReport.Source.SCHEDULER, message=label, stack=traceback.format_exc(),
    )


def _sweep_loop():
    global last_tick_at
    from bookings.services import escalate_unacknowledged_bookings, expire_stale_pending_bookings

    from .services import escalate_stuck_bookings, expire_stale_mpesa_payments, remind_undeposited_cash

    while True:
        time.sleep(SWEEP_INTERVAL_SECONDS)
        last_tick_at = datetime.now(timezone.utc)
        try:
            count = expire_stale_mpesa_payments()
            if count:
                logger.info('Marked %d stale pending M-Pesa payment(s) as failed.', count)
        except Exception:
            _record_sweep_failure('Stale M-Pesa payment sweep failed')

        try:
            remind_undeposited_cash()
        except Exception:
            _record_sweep_failure('Undeposited-cash reminder sweep failed')

        try:
            escalate_stuck_bookings()
        except Exception:
            _record_sweep_failure('Stuck-booking escalation sweep failed')

        try:
            escalate_unacknowledged_bookings()
        except Exception:
            _record_sweep_failure('Unacknowledged-booking escalation sweep failed')

        try:
            count = expire_stale_pending_bookings()
            if count:
                logger.info('Auto-cancelled %d stale unpaid pending booking(s).', count)
        except Exception:
            _record_sweep_failure('Stale pending booking expiry sweep failed')


def start():
    """Called once from PaymentsConfig.ready(). Safe to call more than once - only the first
    call that passes _should_run() actually starts the thread."""
    global _started
    if _started or not _should_run():
        return
    _started = True
    threading.Thread(target=_sweep_loop, daemon=True, name='payments-background-sweep').start()


def is_running():
    return _started
