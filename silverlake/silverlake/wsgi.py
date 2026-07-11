"""
WSGI config for silverlake project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# A real deployment's process manager (gunicorn/uwsgi) should set DJANGO_SETTINGS_MODULE
# itself - this is only the fallback if it doesn't, so it defaults to the safe (hardened) option
# rather than local dev settings.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings.production')

application = get_wsgi_application()
