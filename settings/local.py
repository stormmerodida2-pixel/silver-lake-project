"""
Local development settings - your own machine. Same behavior the project's old single
settings.py had: DEBUG on, sqlite, permissive CORS, no HTTPS enforcement (dev runs over plain
http). Run with:
    python manage.py runserver --settings=settings.local
"""

from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# Vite picks the next free port (5174, 5175, ...) if 5173 is already taken, so allow any
# localhost origin in dev rather than chasing the port number.
CORS_ALLOW_ALL_ORIGINS = True

# The real auth-login rate (10/min in base.py) is meant to slow down brute-forcing a real
# account - it has no purpose against your own machine, and repeatedly re-running the
# Playwright e2e suite (frontend/e2e/) against this server trips it within a couple of runs,
# same false-failure risk the 'test' in sys.argv branch above already works around for the
# Django test suite.
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    scope: '10000/min' for scope in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
}
