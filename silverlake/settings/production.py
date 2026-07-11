"""
Production settings. DEBUG and the HTTPS-hardening flags are hardcoded here, not read from
.env - forgetting or mis-setting a DEBUG value in .env can never accidentally leave a live
deployment open the way it could when settings.py read DEBUG from .env unconditionally. Run
with (though a real deployment should run behind gunicorn/uvicorn, not runserver - see
silverlake/wsgi.py and asgi.py, which already default to this module):
    python manage.py runserver --settings=settings.production
"""

from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = False

# No default - fail loudly at startup rather than silently allowing every Host header through.
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())

# HTTPS enforcement - always on here, never conditional.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year - browsers remember to always use https for this site
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
# Only needed if deployed behind a reverse proxy/load balancer that terminates TLS itself and
# forwards plain http internally (Render, Railway, Heroku, an nginx front end, etc.) - without
# this, SECURE_SSL_REDIRECT would redirect-loop forever since Django never sees the request as
# secure. Leave this off (default) for a direct-to-Django HTTPS setup, e.g. a VPS terminating
# TLS in Django/gunicorn itself.
if config('BEHIND_HTTPS_PROXY', default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
