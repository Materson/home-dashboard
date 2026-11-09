# Project conventions (read first)

Full plan: `docs/PLAN.md`. The sections below are the non-obvious rules — the
plan has the *what*, this file has the *how we write it*.

## Layering per Django app
`models.py` → `selectors.py` (reads, always take `ctx: AccessContext`) →
`services.py` (writes, take `ctx`, run in a transaction) →
`api.py` (thin Ninja router; no business logic) and
`assistant/tools/*.py` (thin AI tool wrappers).

REST endpoints and AI tools **must** call the same selectors/services.
No permission checks in `api.py` beyond `ctx = get_ctx(request)`; the selectors
and services do the work via `ctx.scope(...)` / `ctx.require(...)`.

## Money
Always `apps.core.money.Money` (Decimal + currency code). Never float. Default
currency PLN; every API payload serializes as `{"amount": "123.45", "currency": "PLN"}`.

## Attachments
Never serve via `MEDIA_URL`. Use `apps.core.media.serve_protected` which checks
permissions then returns `X-Accel-Redirect` to the internal nginx location
`/protected-media/`.

## Secrets at rest
API keys, OAuth refresh tokens, webhook secrets: `apps.core.crypto.EncryptedTextField`
(Fernet, key from `FIELD_ENCRYPTION_KEY`). Never log the plaintext.

## IDs
UUIDv7 primary keys for anything exposed in a URL or an API payload
(`apps.core.models.UUIDModel`). Integer PKs stay for join tables only.

## Migrations
One migration per logical change, named verb-noun. Data migrations use
`RunPython` with a forward and a reverse; the reverse may be `noop` only for
seed data.

## Tests
`pytest` + `factory_boy`. Every selector/service that takes `ctx` needs at
least one *negative* permission test (wrong role/person/date window → filtered
or 403). The permission matrix in `tests/test_permissions.py` is parametrized;
add a row rather than a new file when you add an endpoint.

## Code style
`ruff` (format + lint) with the config in `backend/pyproject.toml`. Line length
100. Type hints required on anything in `selectors.py`, `services.py`,
`api.py`, `tools/*.py`. `from __future__ import annotations` at the top of
every module that uses them.

## Frontend
TypeScript strict. API client generated from the Ninja schema
(`npm run gen:api`). Never hand-write request types that match the backend.
Mantine components first; only drop to raw HTML when Mantine doesn't cover it.
Translations live in `src/i18n/{en,pl}/*.json`. Hard-coded strings in
components are a lint error.

## Commits
Conventional commits: `feat(app): …`, `fix(app): …`, `chore: …`, `docs: …`.
One milestone per PR when squashable; otherwise one logical change per commit.
