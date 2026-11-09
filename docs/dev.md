# Developer setup

## Prerequisites
- Python 3.13 (e.g. via `uv python install 3.13`)
- Node 22
- `uv` ( https://docs.astral.sh/uv/getting-started/installation/ )
- MariaDB (optional in dev — defaults to SQLite until `DATABASE_URL` is set)

## First run

```powershell
cp .env.example .env
# Generate a Fernet key for FIELD_ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste into .env.

cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py seed_roles
uv run python manage.py createsuperuser
uv run python manage.py runserver 0.0.0.0:8000

# second terminal:
cd frontend
npm install
npm run gen:api
npm run dev
```

Open http://localhost:5173.

## Common commands

| Command | Does |
|---|---|
| `uv run python manage.py migrate` | apply DB migrations |
| `uv run python manage.py seed_roles` | re-run the role template seed (idempotent) |
| `uv run pytest` | run the Python test suite |
| `uv run ruff check . && uv run ruff format .` | lint + format |
| `uv run celery -A config worker -l info` | run a Celery worker locally |
| `uv run celery -A config beat -l info` | run beat |
| `npm run gen:api` | regenerate the typed API client from the backend |
| `npm run test` | Vitest |
| `npm run build` | production build of the SPA |

## Running the full stack

```powershell
docker compose build
docker compose up -d db redis backend worker beat web backup
```

Follow `docs/network-setup.md` to expose it over HTTPS.
