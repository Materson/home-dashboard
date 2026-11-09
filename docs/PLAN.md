# Home Dashboard — Architecture & Implementation Plan

## Context

Greenfield project (empty `c:\Users\Mateusz\Documents\testy\home-dashboard`). Goal: a self-hosted family dashboard on a QNAP NAS (Docker + MariaDB in its own container) covering cars, health, finance (incl. loans), household stock, Google Calendar, notes/reminders, and an AI assistant that can answer questions, add data and parse photos/documents — with per-user, per-module, per-person and time-range permissions, and privacy controls for what reaches cloud LLMs.

Decisions confirmed with the user:
- **Backend:** Django + Django Ninja (Pydantic, FastAPI-style typed API, OpenAPI). **Frontend:** React SPA (TypeScript, Vite, Mantine, TanStack Query), installable PWA.
- **AI:** Hybrid and **provider-agnostic** — OpenAI (ChatGPT), Anthropic (Claude), Google (Gemini), Ollama or any OpenAI-compatible endpoint; providers are added and chosen later in the Settings UI. Modules can be pinned to a local model.
- **Notifications:** Email, Web Push (PWA), Slack (also a second chat interface to the AI agent).
- **Network:** LAN + the user's existing VPN only; existing **AdGuard** (DNS) and **Nginx Proxy Manager** with Cloudflare-based SSL in front of the stack.

Defaults I'm choosing (easy to change): single household (no multi-tenancy), PLN default currency with a currency field on money, UI i18n-ready with EN + PL.

---

## 1. Deployment architecture (docker-compose on QNAP Container Station)

```
 Phone/PC (LAN or VPN)
   │  DNS: AdGuard rewrite dashboard.<your-domain> → NAS LAN IP
   ▼
 Nginx Proxy Manager (existing, Cloudflare SSL) ──► web (nginx, the only published port)
                                                      ├─ /            static React build (PWA)
                                                      ├─ /api, /admin ─► backend (Django ASGI, uvicorn)
                                                      └─ /protected-media (internal; X-Accel-Redirect after permission check)
 backend ─► mariadb (internal net only) ─ redis ─ /media volume
 worker (Celery) + beat (1-min tick) + slackbot (Slack Bolt, Socket Mode, outbound only)
 ollama (optional profile; or an external GPU PC via its URL in AI settings)
 backup (nightly mariadb-dump + media → QNAP share, encrypted, rotated)
```

- One backend image runs as `backend`, `worker`, `beat`, `slackbot` (different commands) — one codebase, one dependency set.
- MariaDB 11.x LTS and Redis live on an internal Docker network only; the stack publishes just the `web` port (bound to the NAS LAN IP) for Nginx Proxy Manager to target.
- **Attachments (health documents, receipts) are never served as public static files:** Django checks permissions, then hands the file to nginx via `X-Accel-Redirect`.
- **HTTPS via the existing setup:** NPM proxy host `dashboard.<your-domain>` with a **Let's Encrypt certificate issued via Cloudflare DNS-01** (browser-trusted; a Cloudflare *Origin CA* cert would not be trusted by phones when accessed directly). AdGuard DNS rewrite resolves the name to the LAN IP; no public A record needed. Add an NPM access list restricted to LAN + VPN subnets as defense in depth. This valid HTTPS + public-TLD name is what makes service workers, web push (iOS PWA), phone camera upload and the Google OAuth redirect URI work.
- NPM settings for this host: websockets not required; chat streaming uses SSE, so the backend sends `X-Accel-Buffering: no` (and/or disable proxy buffering on the `/api/assistant/` location); raise `client_max_body_size` for uploads (e.g. 25 MB).
- No inbound internet needed: Slack uses Socket Mode; Google Calendar uses polling (push webhooks would need a public endpoint).
- Images built multi-arch (`docker buildx`, amd64 + arm64) so they run regardless of the QNAP CPU. Recommend a QNAP encrypted volume for `/media` + DB data, and an HBS3 off-device copy of backups.

## 2. Backend structure (Django 5.2 LTS, Python 3.13, uv, ruff, pytest)

```
backend/
  config/            settings/{base,dev,prod}.py, asgi.py, celery.py, urls.py (Ninja API mounted at /api)
  apps/
    core/            TimeStamped/Archivable base models, Money (DECIMAL(12,2)+currency), Attachment (generic FK), audit, Fernet field encryption
    accounts/        custom User (email login), django-allauth *headless* (SPA login, TOTP 2FA, recovery codes, rate limits), invites only
    people/          Person (name, birth_date, color/avatar, optional 1:1 User)
    access/          AccessGrant, AccessContext, role templates (see §3)
    finance/         Category, Transaction, RecurringRule, Loan(+RateChange, Overpayment), Investment (later)
    cars/            Car, OdometerReading, FuelEntry, MaintenanceEvent, OilChange/OilTopUp, Inspection, CarEvent
    health/          MedicalRecord, Medication(+Purchase), Appointment, TestResult(+LabValue)
    household/       Item, StockBatch (qty, purchase/expiry date), ShoppingList
    notes/           Note (owner-private, shareable), quick-add NL parser (dateparser, PL+EN)
    reminders/       Reminder engine (time-based + odometer-based), dispatch
    notifications/   channels: email, webpush (pywebpush+VAPID, PushSubscription), slack; per-user prefs
    gcal/            Google OAuth, calendar selection, incremental sync cache, create/delete, week summary
    assistant/       provider profiles, LLM gateway, tool registry, privacy layer, conversations, PendingAction, ingestion
    slackbot/        Bolt app (management command), account linking, DM chat relay, interactive buttons
```

**Per-app layering (the key convention):** `models.py` → `selectors.py` (read queries, always scoped by `AccessContext`) → `services.py` (writes/business logic, take `ctx`) → `api.py` (thin Ninja routers) and `assistant/tools/*.py` (thin AI tool wrappers). REST endpoints and AI tools call the **same** selectors/services, so permissions are enforced in one place.

**Cross-module integration (one helper each, reused everywhere):**
- `finance.services.upsert_linked_transaction(ctx, source_obj, amount, category_key, person, date)` — Transaction has a generic `source` FK; fuel, maintenance, inspection, medication purchase call it. Editing/deleting the source updates/removes the transaction. Seeded system categories (`car.fuel`, `car.maintenance`, `health.medicines`, …).
- `reminders.services.schedule(ctx, target_obj, due_at=None, due_odometer_km=None, recurrence=None, recipients, channels, sensitivity)` — used by oil change, inspection, appointment, expiring stock, notes.

**Background jobs (Celery + Redis):** `beat` ticks every minute → `dispatch_due_reminders` (DB is the source of truth; `SELECT … FOR UPDATE SKIP LOCKED`, no long Celery ETAs); daily: materialize recurring transactions/loan installments, expiry scan; every 10 min: Google Calendar incremental sync (syncToken). Worker also runs AI document ingestion.

## 3. Auth & permissions model

- **Login:** django-allauth headless + session cookie (HttpOnly, Secure, SameSite=Lax, CSRF) served from the same origin as the SPA — no JWTs in localStorage. Argon2 hashing, TOTP 2FA (enforce for adults), login rate limiting, admin creates accounts/invites (no open signup). People without login are just `Person` rows.
- **AccessGrant** (the editable permission unit):

  | field | meaning |
  |---|---|
  | grantee | a User **or** a Group (Django Group = "Parents", "Children", custom) |
  | module | finance / cars / health / household / calendar / notes / assistant / admin |
  | level | view / edit / manage |
  | effect | allow / deny (deny wins; default is deny-all) |
  | subjects | all persons / self only / selected Persons (person-centric modules); selected cars for cars |
  | data_from / data_to | optional record-date window ("can see health data from 2024 on") |
  | valid_until | optional expiry of the grant itself |

- **AccessContext** built per request (and per Slack message / AI tool call) = user's merged grants. Models declare `scope_person_field` / `scope_date_field`; `ctx.scope(module, queryset, level)` applies person + date filters, `ctx.require(module, level, obj)` guards writes. Nav/menu and AI tool list are derived from the same context.
- **Seeded role templates:** *Admin* (manage users/grants, AI providers), *Parent* (all modules, all persons, edit), *Child* (health: self/view; household: edit; notes & calendar: own). All editable in a Settings → Access UI.
- Auditing: django-auditlog on sensitive models + access log of every LLM call.

## 4. Module scope (data + features)

1. **Cars:** add/edit/archive; odometer readings (manual, from fuel entries, from photo); fuel entries (litres, price/l, total, full-tank flag → L/100 km full-to-full, cost → finance); maintenance (part replacement with optional cost → finance); oil change (oil spec, next due km and/or date → reminder; top-up history between changes); technical inspection (cost, valid-until → reminder); free-form events/issues; dashboard: km to next oil change (with ETA from average daily km), monthly fuel cost, consumption trend.
2. **Health:** persons; medical history CRUD (illness/condition, dates, notes, attachments); medications (name, dosage, schedule, linked to illness, purchases → finance); appointments (→ Google Calendar event + reminders); test results (file + parsed `LabValue` rows with units/reference ranges → trend charts).
3. **Finance:** income/expense with name, person, category (user-defined tree), notes, attachments; recurring rules (rrule) materialized as "expected" entries to confirm; search (name/notes text, date range, amount min/max, category, person); charts (monthly by category, income vs expense, per-person); **loans**: annuity/decreasing installments, variable-rate changes, overpayments with *shorten term* vs *reduce installment* and a side-by-side interest-savings simulation — pure-Decimal `finance/loans/schedule.py`, heavily unit-tested; investments (simple holdings + value snapshots) as a later add-on.
4. **Household:** items (name, category, location, unit, min quantity), stock batches with expiry; warnings when expiry is near or stock < min; auto shopping list.
5. **Google Calendar:** OAuth "Web application" client (redirect URI `https://dashboard.<your-domain>/api/gcal/callback`), tokens Fernet-encrypted; choose calendars, cached events, week summary view, add/delete events; appointments and selected reminders sync as events. Publish the Google OAuth app to "In production" (unverified is fine for personal use) — in "Testing" mode refresh tokens expire after 7 days.
6. **Notes/Reminders:** quick-add bar with natural-language time parsing without AI ("ciasto w piekarniku za 40 min", "remember to buy milk tomorrow 18:00"); notes private by default, shareable with users/groups; reminders with snooze/done from web push and Slack buttons.
7. **Home overview page:** upcoming reminders, this week's calendar, low/expiring stock, month spend vs budget, km to next service.

## 5. AI assistant (answers to your questions)

**Should it use an MCP server?** Not for the in-app agent. The agent runs inside the backend with an **internal tool registry** — each tool is a thin wrapper over existing selectors/services and executes with the *requesting user's* `AccessContext`. MCP would only add a hop and a second auth surface, and cloud providers' hosted MCP connectors call servers from their cloud, which can't (and shouldn't) reach a LAN-only NAS. Optional later: expose the same registry as an MCP endpoint (`/mcp`, per-user scoped personal access tokens) for local clients (Claude Desktop, ChatGPT desktop, IDE agents) over your VPN.

**Provider-agnostic LLM layer (configure later):**
- Gateway built on **pydantic-ai** — one Pydantic-native API over OpenAI, Anthropic, Google Gemini, Ollama and any OpenAI-compatible server (LM Studio, vLLM…), covering tool calling, structured outputs, image/PDF input and streaming. Wrapped in our own `assistant/llm/gateway.py` so the rest of the code never imports a vendor SDK (swappable if the library ever stops fitting).
- **Settings → AI (admin only):** add *provider profiles* — type (OpenAI / Anthropic / Gemini / Ollama / OpenAI-compatible), base URL, API key (Fernet-encrypted, never returned to the browser), model name, class **cloud** or **local**, capability flags (tools, vision, PDF) + a "Test connection" button.
- **Assignments:** which profile is used for *chat*, *document extraction*, and *private (local) mode*; optional fallback profile. Until something is configured, AI features are simply hidden — the rest of the dashboard works without AI.
- Capability-aware: if the assigned model lacks vision, ingestion runs local OCR (Tesseract) and sends text only.

**Security & permission design (independent of provider):**
- **Tools offered = tools the user's grants allow** (a child never even sees finance tools) **and** that the current provider class may receive. Read tools return minimal, aggregated fields with row limits (`finance_summary`, `search_transactions`, `car_status` → km to oil change, `health_history`, `medications_in_period`, `low_stock`, `calendar_week`). No raw SQL, no DB access, **no outbound tools** (no web fetch, no email to arbitrary addresses) — so even a prompt-injected document has no way to exfiltrate data.
- **Writes:** tools never write directly; they create a `PendingAction` (proposed record shown as a pre-filled form card in chat / Slack buttons) that the user confirms or edits. Exception: self-only notes/reminders/shopping-list adds auto-execute with Undo.
- Every tool call passes through: permission check → privacy filter → audit log → (writes) confirmation gate. Conversations are private to their owner.

**Not exposing private data to cloud models:**
- Per-module AI policy: `ai_enabled`, `cloud_allowed` (default: Health = local-only; others cloud-allowed), per-user override.
- A conversation runs in *Cloud* or *Private (local)* mode; tools for modules not allowed on the current provider class are not offered, and the UI suggests switching to Private mode.
- Pseudonymization: names/nicknames of People in user messages and tool results are replaced by stable aliases (`Person_A`) before leaving the NAS and re-hydrated in the reply; tools never return identifiers (PESEL, addresses, phone, VIN/plates, account numbers).
- Provider terms differ — prefer paid API tiers (e.g. Gemini's free tier may use prompts for product improvement; OpenAI/Anthropic APIs don't train on API data by default). The settings page shows each profile's class, and every LLM call is logged with provider + which modules' data were sent.

**Document/photo ingestion:** upload (web/PWA camera or Slack) → `Attachment` → Celery job → user-selected or auto-detected type (fuel receipt, odometer, invoice, lab result) → routing by module policy (lab results → local model, or local OCR + redaction → cloud text-only) → structured extraction into a Pydantic schema per type → `PendingAction` with the image side-by-side for review → save, attachment linked to the record.

**Chat UI:** SSE streaming from an async Ninja endpoint, rendered in the SPA and relayed to Slack DMs.

## 6. Slack integration

Slack Bolt in Socket Mode (outbound WebSocket, works behind your VPN/NAT). Features: account link via one-time code from Settings; DM-only chat with the agent (group channels rejected so others can't see answers); photo/file DM → ingestion pipeline; reminder DMs with Done / Snooze / Open buttons; confirm `PendingAction`s with buttons. Privacy: Slack is a cloud service, so reminders with `sensitivity=private` (health by default) are delivered as "You have a reminder — open dashboard", and health answers are only sent to Slack if the user enables it.

## 7. Frontend (React 19 + TS + Vite)

- Mantine (components, forms, dates, charts, notifications, dropzone, spotlight search), TanStack Query, React Router, react-i18next (EN/PL), vite-plugin-pwa (installable, service worker for web push, camera upload via `<input capture>`).
- **Typed API client generated from Django Ninja's OpenAPI** (`openapi-typescript` + `openapi-fetch`) — backend schema changes surface as TS errors, which keeps React work low-risk for a Python-first developer.
- `src/features/<module>/` per module (pages, forms, hooks); shared `components/` (DataTable with filters, MoneyInput, PersonSelect, AttachmentDropzone, ConfirmActionCard); route guards and nav built from `/api/me/permissions`.

## 8. Milestones (each one usable on its own)

| # | Delivers |
|---|---|
| M0 Foundation | git repo, docker-compose (db, redis, backend, worker, beat, web, backup), Django skeleton, allauth headless + TOTP, People, AccessGrant/AccessContext + role seeds, Attachments (protected media), Reminder engine + email & web push, SPA shell (login, layout, permission-driven nav, overview page), NPM/AdGuard setup notes |
| M1 Finance | categories, transactions, persons, search, recurring, charts, loans + overpayment simulator |
| M2 Cars | cars, fuel, odometer, maintenance, oil (km/date reminders), inspection, events; finance links |
| M3 Health | records, medications (+cost), appointments, test results with lab-value trends |
| M4 Household | items, stock batches, expiry warnings, shopping list |
| M5 Notes + Google Calendar | notes, NL quick-add reminders, OAuth, sync, week summary, add/delete, appointment sync |
| M6 AI assistant | provider profiles UI, gateway, tool registry, privacy layer, chat UI (SSE), PendingActions, ingestion (fuel receipt, odometer, lab result) |
| M7 Slack | bot, linking, notifications, chat relay, file intake |
| M8 Extras | investments, optional MCP endpoint, budgets |

## 9. Critical files (created in M0, patterns reused by all modules)

- `docker-compose.yml`, `.env.example`, `web/nginx.conf` (SPA + `/api` proxy + internal protected media), `backend/Dockerfile`, `web/Dockerfile` (Node build stage → nginx), `docs/network-setup.md` (NPM proxy host, Cloudflare DNS-01 cert, AdGuard rewrite, access list)
- `backend/config/settings/base.py`, `backend/config/celery.py`, `backend/config/urls.py`
- `backend/apps/access/context.py` (AccessContext, `scope`/`require`), `backend/apps/access/models.py` (AccessGrant)
- `backend/apps/core/models.py` (base models, Money, Attachment), `backend/apps/core/crypto.py` (Fernet fields)
- `backend/apps/reminders/services.py` + `tasks.py`; `backend/apps/notifications/channels/*.py`
- `backend/apps/finance/services.py` (`upsert_linked_transaction`), `backend/apps/finance/loans/schedule.py`
- `backend/apps/assistant/{models.py (ProviderProfile, Assignment, PendingAction), llm/gateway.py, tools/, privacy.py, loop.py}`
- `frontend/src/api/` (generated), `frontend/src/app/` (router, auth, layout), `frontend/src/features/*`

## 10. Verification

- **Automated (pytest + factory_boy):** permission matrix tests (role × module × endpoint × person × date window → expected 200/403/filtered results) run against both REST endpoints and AI tools; loan schedule tests against a real bank schedule; fuel-consumption and oil-due calculations; reminder dispatch idempotency; AI tests with a fake model (pydantic-ai test model): tools filtered by grants and provider class, pseudonymization round-trip, writes produce PendingActions, local-only modules never reach a cloud profile; protected media returns 403 for unauthorized users.
- **Frontend:** Vitest for hooks/utilities; Playwright smoke (login + 2FA, add fuel entry → transaction appears, child account cannot open Finance).
- **End-to-end on the NAS:** `docker compose up -d` → `migrate` → seed roles → create admin; add NPM proxy host + AdGuard rewrite; open `https://dashboard.<your-domain>` from a phone over VPN, install the PWA, receive a test web push; set a 2-minute "cake" reminder and get it via push + email + Slack; connect Google Calendar and add/delete an event; add an AI provider profile, "Test connection", upload a fuel receipt photo and confirm the extracted entry; ask the agent "how many km to the next oil change" and, as a child account, verify it can't answer finance questions; restore a backup into a fresh stack.
