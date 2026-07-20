"""
Production settings. DEBUG and the HTTPS-hardening flags are hardcoded here, not read from
settings/.env - forgetting or mis-setting a DEBUG value there can never accidentally leave a live
deployment open the way it could when settings.py read DEBUG from it unconditionally. Run
with (though a real deployment should run behind gunicorn/uvicorn, not runserver - see
silverlake/wsgi.py and asgi.py, which already default to this module):
    python manage.py runserver --settings=settings.production

Every config() call below reads from settings/.env specifically (see the note in base.py above
BASE_DIR) - not settings/.env.example, which is just the template documenting what keys exist.
"""

from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = False

# No default here either - base.py's own SECRET_KEY default is a real value committed in plain
# text to this (public) repo, harmless for local dev but a genuine hole if it ever silently
# became the key protecting real sessions/CSRF tokens/password-reset links. Fail loudly instead.
SECRET_KEY = config('SECRET_KEY')

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

# Serves STATIC_ROOT directly from the app process (compressed, far-future cache headers) -
# must sit right after SecurityMiddleware. runserver's own dev static-file handling in
# settings.local/development is unaffected - this only matters behind gunicorn. Has nothing to
# do with MEDIA_ROOT (uploaded photos/documents) - see the storage backend below for that.
MIDDLEWARE = MIDDLEWARE.copy()
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
# Copied rather than mutated in place - MIDDLEWARE/STORAGES/DATABASES here are the exact same
# objects base.py built (from .base import * doesn't copy), so writing into them directly would
# reach back and change base.py's own module-level state.
STORAGES = STORAGES.copy()
STORAGES['staticfiles'] = {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}

# MySQL - set DATABASE_URL and this replaces base.py's SQLite config entirely. Format:
# mysql://USER:PASSWORD@HOST:PORT/NAME (dj-database-url auto-detects the engine from the
# scheme - the mysqlclient driver in requirements.txt is what actually makes mysql:// work).
# Left unset, production still runs on SQLite - not recommended for real use (most hosts wipe
# local disk on every deploy), but not hard-blocked either, since a low-traffic single-instance
# deployment can technically still work with it.
# BookingViewSet.create()'s double-booking guard (an UPDATE against the vehicle row as the first
# statement in the transaction) works correctly here too, without changes - MySQL's InnoDB engine
# takes a real per-row lock on that UPDATE, so a second concurrent request for the same vehicle
# blocks on it exactly as intended, more precisely than SQLite's whole-database lock.
# innodb_lock_wait_timeout caps how long it'll wait before raising OperationalError (MySQL error
# 1205), which that same view already turns into a clean 409 rather than leaving the request
# hanging.
DATABASE_URL = config('DATABASE_URL', default='')
if DATABASE_URL:
    import dj_database_url

    DATABASES = DATABASES.copy()
    DATABASES['default'] = dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    db_options = DATABASES['default'].setdefault('OPTIONS', {})
    # STRICT_TRANS_TABLES: RDS's default parameter group doesn't set this, so without it MySQL
    # silently truncates/coerces invalid data on insert (e.g. a too-long string) instead of
    # raising an error Django would otherwise catch - exactly the class of bug Django's own
    # mysql.W002 system check warns about.
    db_options['init_command'] = (
        "SET SESSION innodb_lock_wait_timeout=10, SESSION sql_mode='STRICT_TRANS_TABLES'"
    )
    # RDS's own recommended connection mode verifies the server's identity against Amazon's CA
    # bundle - baked into the Docker image at this exact path (see the Dockerfile). Skipped
    # entirely for a non-RDS MySQL host (e.g. local testing against a plain MySQL container),
    # where this file won't exist and isn't needed.
    rds_ca_bundle = BASE_DIR / 'global-bundle.pem'
    if rds_ca_bundle.exists():
        db_options['ssl'] = {'ca': str(rds_ca_bundle)}

# S3-compatible object storage for media - works with real AWS S3, Cloudflare R2, DigitalOcean
# Spaces, Backblaze B2, or anything else speaking the S3 API, by pointing AWS_S3_ENDPOINT_URL at
# that provider (leave it unset for real AWS S3). Left entirely unset, base.py's local-disk
# storage is used instead - fine for a quick test deploy, but most production hosts wipe local
# disk on every deploy, so this must be set before going live for real.
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
if AWS_STORAGE_BUCKET_NAME:
    STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}
    AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID', default='')
    AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY', default='')
    AWS_S3_ENDPOINT_URL = config('AWS_S3_ENDPOINT_URL', default='') or None
    AWS_S3_REGION_NAME = config('AWS_S3_REGION_NAME', default='auto')
    AWS_S3_FILE_OVERWRITE = False
    # No ACL is set at all, not even "private" - some providers (Cloudflare R2) reject the ACL
    # header outright, and bucket-level access (not per-object ACLs) is what actually controls
    # who can reach a file. django-storages' own default is signed, expiring URLs, which matters
    # here since MEDIA holds public marketing images (vehicle photos) and private compliance
    # documents (driver licenses, logbooks, insurance certs) side by side in the same bucket.

# Error tracking (Sentry) - without this, an unhandled exception in production is only ever
# discovered when a user complains, not when it actually happens. Left unset, nothing below runs
# at all - local dev and any deploy that hasn't set SENTRY_DSN stays completely untouched, same
# pattern as email/M-Pesa/S3 above.
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        environment=config('SENTRY_ENVIRONMENT', default='production'),
        # A modest sample of transactions for performance monitoring, not every single request -
        # errors themselves are always captured regardless of this; only tune it upward if
        # Sentry's own quota/cost tolerates the extra volume.
        traces_sample_rate=config('SENTRY_TRACES_SAMPLE_RATE', default=0.1, cast=float),
        # This app's own request bodies routinely carry driver licenses, ID documents, and
        # customer contact details - never let an error report also become a second place those
        # end up, even inside SilverLake's own Sentry project.
        send_default_pii=False,
    )
