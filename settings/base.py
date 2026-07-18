"""
Django settings shared by every environment for the silverlake project.

This file is never used directly (there's no bare DJANGO_SETTINGS_MODULE=settings.base) - each
environment file in this package (local.py, development.py, production.py) does `from .base
import *` and then overrides whatever actually differs for that environment: DEBUG,
ALLOWED_HOSTS, CORS, and the HTTPS-hardening flags. Run with e.g.:
    python manage.py runserver --settings=settings.local
"""

import sys
from datetime import timedelta
from pathlib import Path

from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# This file lives at <project root>/settings/base.py, so two `.parent`s gets back to
# <project root> - the same directory manage.py, db.sqlite3, and media/ live in.
BASE_DIR = Path(__file__).resolve().parent.parent

# The real env file lives at settings/.env (next to this file), not the project root.
# decouple's config() is a process-wide singleton that, on its first call anywhere in the app,
# searches upward starting from the CALLING file's own directory - since this is that first call
# and this file lives in settings/, it finds settings/.env directly. Every other module's own
# `from decouple import config` reuses this same cached lookup, so this is the only place the
# path is ever resolved. Do not add a stray/empty .env anywhere between here and the filesystem
# root - decouple stops at the first file it finds, even if it's empty.

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY', default='django-insecure-j4v=c0*78mzij*cq8*3abgz^z$b13bll(1@kxlu!tb(42&oqi1')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',

    'accounts',
    'fleet',
    'drivers',
    'bookings',
    'payments',
    'reviews',
    'announcements',
    'blog',
    'notifications',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Rates for the specific public-facing views that set throttle_classes/throttle_scope
    # themselves (login, registration, password reset, the M-Pesa STK push triggers, and the
    # public driver application form) - everything else is unthrottled.
    'DEFAULT_THROTTLE_RATES': {
        'auth-login': '10/min',
        'auth-register': '5/hour',
        'auth-password-reset': '5/hour',
        'mpesa-stk': '5/min',
        'token-payment-view': '20/min',
        'driver-application': '5/hour',
        'payment-dispute': '10/hour',
    },
}

SIMPLE_JWT = {
    # Short-lived on purpose - the frontend's axios interceptor silently refreshes on a 401,
    # so there's no UX cost to keeping this tight. A short-lived access token also limits how
    # long a stolen one keeps working even after the refresh token behind it gets blacklisted
    # (see accounts.services.blacklist_all_tokens_for_user) - blacklisting only stops a refresh
    # token from minting new access tokens, it can't revoke an access token already issued.
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=14),
}

# Gmail SMTP for activation/password-reset emails.
# EMAIL_HOST_USER must be a full Gmail address; EMAIL_HOST_PASSWORD must be a 16-character
# Google "App Password" (requires 2FA enabled on that account) - NOT the normal account password.
# Generate one at https://myaccount.google.com/apppasswords
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER or 'noreply@silverlakecarrentals.co.ke')

# Until real Gmail credentials are set, write emails to disk instead of crashing on send
# (the dev server runs in the background, so console output isn't visible to test against -
# check silverlake/sent_emails/ for the activation/reset link while testing).
if 'test' in sys.argv:
    # Never hit real SMTP (or write to disk) from the automated test suite.
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    # The full PBKDF2 iteration count is unnecessary (and slow) for tests that create lots
    # of throwaway users - this hasher is only used when 'test' is in sys.argv.
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
    # Throttle state persists in the cache across test methods within the same run - without
    # this, tests that hit a throttled view more than a handful of times would start failing
    # on request count alone, not on what they're actually testing.
    REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
        scope: '10000/min' for scope in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
    }
elif EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    EMAIL_FILE_PATH = BASE_DIR / 'sent_emails'

# Where the SPA lives, so emails can link back to activation/reset pages.
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:5173')

ROOT_URLCONF = 'silverlake.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'silverlake.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # SQLite locks the whole database on the first write in a transaction (see
        # BookingViewSet.create(), which deliberately relies on this to prevent double-booking
        # a vehicle). Without a generous timeout, a second connection hitting that lock fails
        # immediately with "database is locked" instead of waiting for the first transaction
        # to finish - bump it well past how long a booking request should ever take.
        'OPTIONS': {'timeout': 20},
    }
}
# Swapped for Postgres in production - see settings/production.py.


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Nairobi'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # populated by `manage.py collectstatic`; unused until production.py's whitenoise is in play

# Media files (uploaded vehicle/driver photos, driver/compliance documents)
MEDIA_URL = 'media/'
if 'test' in sys.argv:
    # Without this, every test that uploads a file (vehicle photos, driver logbooks, avatars,
    # ...) writes a real file into the real media/ folder on disk, individually harmless but
    # accumulating with every test run since nothing ever cleans them up - a tempfile.mkdtemp()
    # gets discarded by the OS instead.
    import tempfile
    MEDIA_ROOT = Path(tempfile.mkdtemp(prefix='silverlake_test_media_'))
else:
    MEDIA_ROOT = BASE_DIR / 'media'
# Swapped for S3-compatible object storage in production - see settings/production.py.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
