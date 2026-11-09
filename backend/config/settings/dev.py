from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import DATABASES, INSTALLED_APPS, MIDDLEWARE

DEBUG = True
ALLOWED_HOSTS = ["*"]
SECRET_KEY = "dev-only-secret-not-for-production"
CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
SPA_ORIGIN = "http://localhost:5173"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# use sqlite by default in dev so you can `uv run python manage.py migrate`
# without needing MariaDB running — switch to MariaDB with DATABASE_URL in .env
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"]["OPTIONS"].pop("init_command", None)
    DATABASES["default"]["OPTIONS"]["init_command"] = "SET sql_mode='STRICT_TRANS_TABLES'"

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# noisy local SQL in dev is handy
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

# allow the vite dev server to make cookie'd requests
INSTALLED_APPS += []  # placeholder for dev-only apps
MIDDLEWARE += []
