# Home Dashboard

Self-hosted family dashboard for a QNAP NAS: cars, health, finance (incl. loans),
household stock, Google Calendar, notes/reminders, and a provider-agnostic AI
assistant that can answer questions, add data and parse photos/documents.

Backend: Django 5.2 + Django Ninja, MariaDB, Celery/Redis.
Frontend: React 19 + TypeScript + Vite + Mantine (PWA).
Deployment: docker-compose behind an existing Nginx Proxy Manager + AdGuard.

See `docs/PLAN.md` for the full architecture and `CLAUDE.md` for conventions.

## Quick start (dev)

```powershell
cp .env.example .env
docker compose up -d db redis
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py seed_roles
uv run python manage.py createsuperuser
uv run python manage.py runserver 0.0.0.0:8000
# in another terminal
cd frontend
npm install
npm run dev
```

## Full stack (NAS)

```powershell
docker compose build
docker compose up -d
```

Then follow `docs/network-setup.md` to publish `dashboard.<your-domain>` through
Nginx Proxy Manager with a Let's Encrypt (Cloudflare DNS-01) certificate, and
add an AdGuard rewrite to your LAN IP.
