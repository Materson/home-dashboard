#!/bin/sh
# The backend container's start: bring the database up to date (migrations,
# the default roles), copy the Django admin's static files for nginx, serve.
# A fresh install then needs nothing but opening the app (first-time setup).
set -eu

python manage.py migrate --noinput
python manage.py seed_roles
python manage.py collectstatic --noinput --verbosity 0

exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips '*'
