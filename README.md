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
uv run python manage.py runserver 0.0.0.0:8000
# in another terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173: with no account yet, the app starts first-time
setup (your admin account, then the family). Accounts, roles and access are
managed in the app (Settings), no Django admin needed.

## On the NAS (Portainer)

**[docs/deploy-nas.md](docs/deploy-nas.md)** — the GitHub repo and releases
(a tag builds the images), the Portainer stack (`deploy/docker-compose.yml`,
settings as stack variables), first-time setup, every update after, backups
and restore.

## Full stack on this PC

```powershell
docker compose build
docker compose up -d
```

The backend applies migrations and the default roles every time it starts.
Open the dashboard: a fresh install shows first-time setup — whoever opens it
first creates the admin account, so do it right after starting the stack.
Family members get their logins in Settings → Accounts as one-time links (no
email needed); a forgotten password is a new link from there too.

Then follow `docs/network-setup.md` to publish `dashboard.<your-domain>` through
Nginx Proxy Manager with a Let's Encrypt (Cloudflare DNS-01) certificate, and
add an AdGuard rewrite to your LAN IP.
