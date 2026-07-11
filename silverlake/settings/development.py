"""
Development settings - a shared staging/test deployment. There's no separate environment for
this yet (no distinct hosting, no separate .env), so this is just an alias for local.py today -
kept as its own file so `--settings=settings.development` already works the moment a real
staging environment exists, without anyone having to remember to create this file then. Run
with:
    python manage.py runserver --settings=settings.development
"""

from .local import *  # noqa: F401,F403
