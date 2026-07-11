"""In-process background scheduler for periodic cleanup tasks. This project has no Celery/cron
of its own, so rather than requiring someone to configure an external OS-level Task Scheduler or
cron entry (previously the only way payments.services.expire_stale_mpesa_payments actually ran),
a lightweight daemon thread does it automatically for as long as the Django process is alive.

Deliberately not started for management commands (manage.py test/migrate/shell/etc.) - none of
those keep a process running long enough for this to matter, and starting it during `test` in
particular would let a stray background thread touch the test database. Only starts under the
actual long-lived server process (runserver's real worker, or a production WSGI/ASGI process) -
see _should_run().

If this later moves to a multi-process production server (gunicorn with several workers, say),
each worker starts its own copy - slightly redundant (the same sweep runs more than once per
interval), but harmless, since expire_stale_mpesa_payments is just an idempotent UPDATE query.
"""
import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 300

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


def _sweep_loop():
    from .services import expire_stale_mpesa_payments

    while True:
        time.sleep(SWEEP_INTERVAL_SECONDS)
        try:
            count = expire_stale_mpesa_payments()
            if count:
                logger.info('Marked %d stale pending M-Pesa payment(s) as failed.', count)
        except Exception:
            logger.exception('Stale M-Pesa payment sweep failed')


def start():
    """Called once from PaymentsConfig.ready(). Safe to call more than once - only the first
    call that passes _should_run() actually starts the thread."""
    global _started
    if _started or not _should_run():
        return
    _started = True
    threading.Thread(target=_sweep_loop, daemon=True, name='stale-mpesa-payment-sweep').start()
