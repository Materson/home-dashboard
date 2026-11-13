# Deploying to the NAS (Portainer) — and every update after

```
this PC ──git push──▶ GitHub (private repo)
                        ├─ every push: tests (Actions → CI)
                        └─ a tag v1.2.0: tests, then 3 images → ghcr.io (private)
                                                         │
QNAP ─ Portainer stack ◀── pulls deploy/docker-compose.yml + the images
        └─ web :8080 ◀── Nginx Proxy Manager (HTTPS) ◀── phones / PCs (LAN, VPN)
```

Only code goes to GitHub — never your data, `.env` or secrets. The NAS needs
no code and no shell: the backend migrates the database on every start, and
a fresh install opens first-time setup in the browser.

## One-time setup

### 1. GitHub repository

1. On github.com: **New repository** → name `home-dashboard`, **Private**,
   nothing else (no README).
2. On this PC (PowerShell, in the project folder):

   ```powershell
   git remote add origin https://github.com/<you>/home-dashboard.git
   git push -u origin main
   ```

3. The repo's **Actions** tab shows *CI* running the tests — it should be green.

### 2. The first release

```powershell
git tag -a v1.0.0 -m "1.0.0"
git push origin v1.0.0
```

Actions → *Release* runs the tests, then builds three images (5–10 min the
first time). They appear under your GitHub profile → **Packages**:
`home-dashboard-backend`, `-web`, `-backup` (private).

### 3. Tokens for the NAS

GitHub → **Settings → Developer settings → Personal access tokens → Tokens
(classic)** → *Generate new token (classic)*, no expiry (or a long one):

- **Images:** scope `read:packages` only.
- **The compose file:** a second token with scope `repo` (Portainer reads
  `deploy/docker-compose.yml` from the private repo). Or use one token with
  both scopes.

In **Portainer → Registries → Add registry → Custom registry**: name `GitHub`,
URL `ghcr.io`, *Authentication* on, username = your GitHub name, password =
the `read:packages` token.

### 4. Secrets

```powershell
backend\.venv\Scripts\python ops\gen-secrets.py
```

prints `DJANGO_SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, the two MariaDB
passwords, `BACKUP_PASSPHRASE` and the web push keys. **Save them in your
password manager** — `FIELD_ENCRYPTION_KEY` decrypts the stored AI / Google
keys and `BACKUP_PASSPHRASE` opens the backups; without them those are lost.

### 5. A folder for backups

QNAP *File Station*: create e.g. `Backups/home-dashboard` on a share. Its path
inside the NAS is `/share/Backups/home-dashboard` (`/share/<share name>/…`).
Copy it off the NAS too (*HBS 3* → another disk or a cloud).

### 6. The stack

**Portainer → Stacks → Add stack**, name `home-dashboard`:

- **Build method: Repository**
  - URL `https://github.com/<you>/home-dashboard`, reference `refs/heads/main`
  - **Compose path** `deploy/docker-compose.yml`
  - *Authentication* on: your GitHub name + the `repo` token
- **Environment variables** → *Advanced mode*, paste and fill in:

  ```ini
  IMAGE_PREFIX=ghcr.io/<you, lower case>/home-dashboard
  APP_VERSION=latest
  PUBLIC_HOST=dashboard.<your-domain>
  WEB_PORT=8080
  BACKUP_HOST_DIR=/share/Backups/home-dashboard
  TZ=Europe/Warsaw
  # from ops/gen-secrets.py
  DJANGO_SECRET_KEY=
  FIELD_ENCRYPTION_KEY=
  MARIADB_PASSWORD=
  MARIADB_ROOT_PASSWORD=
  BACKUP_PASSPHRASE=
  VAPID_PRIVATE_KEY=
  VAPID_PUBLIC_KEY=
  VAPID_ADMIN_EMAIL=you@example.com
  # optional: e-mail (e.g. a Gmail app password)
  EMAIL_HOST=smtp.gmail.com
  EMAIL_HOST_USER=
  EMAIL_HOST_PASSWORD=
  DEFAULT_FROM_EMAIL=Home Dashboard <you@example.com>
  ```

  Optional too: `GOOGLE_OAUTH_CLIENT_ID` / `_SECRET`, `SLACK_*` (plus
  `COMPOSE_PROFILES=slack` to start the Slack bot). A missing required value
  stops the deploy with a message naming it.
- **Deploy the stack.** The first start pulls the images, creates the
  database and migrates it (1–3 min; *web* starts once the backend is healthy).

Check from the PC: `http://<NAS IP>:8080/api/healthz` →
`{"status": "ok", "version": "1.0.0"}`.

### 7. HTTPS, name, access

Nginx Proxy Manager proxy host → `<NAS IP>` port `8080`, the Let's Encrypt
certificate and AdGuard's rewrite: **[network-setup.md](network-setup.md)**.

### 8. First-time setup

Open `https://dashboard.<your-domain>` **right after deploying** — on a fresh
install whoever opens it first creates the admin account. Then the family
step; later Settings → Accounts for more logins (one-time links).

Log in over the HTTPS name only: the session cookie is HTTPS-only, so
`http://<NAS IP>:8080` shows the app but can't keep you logged in.

## Every update

1. **Code** on this PC, commit, `git push` — *CI* runs the tests.
2. **Release** when CI is green:

   ```powershell
   git tag -a v1.1.0 -m "1.1.0"
   git push origin main v1.1.0
   ```

   and wait for Actions → *Release* to finish (green).
3. **Backup now** (always before an update with migrations): Portainer →
   Containers → `home-dashboard-backup-1` → *Console* → Connect → `backup-now`.
4. **Portainer → Stacks → home-dashboard → Pull and redeploy** (with
   *Re-pull image* on). It fetches the compose file from `main` and the new
   images; the backend migrates, worker / beat / web wait until it's healthy.
5. **Check:** the user menu in the app shows *Wersja 1.1.0*.

Version numbers: `1.0.1` for fixes, `1.1.0` for new features, `2.0.0` when an
update can't be undone without the backup (see below). A tag with a suffix
(`v1.1.0-rc1`) builds images but doesn't move `latest` — try it with
`APP_VERSION=1.1.0-rc1`.

### Going back to an earlier version

Stack → *Environment variables*: `APP_VERSION=1.0.0` → *Update the stack*
(re-pull). That's enough when the newer version only added things (tables,
columns). If it changed data, restore the backup from step 3 (below) with
`APP_VERSION` set to the old version first.

## Writing code so updates stay easy

- **Migrations add, then remove later.** A new column is nullable or has a
  default; drop an old column one release after the code stops using it. A
  data migration has a reverse (CLAUDE.md). Then going back a version works
  without restoring a backup.
- **New settings** get a default, or a `${NAME:?message}` in
  `deploy/docker-compose.yml` and a line in step 6 above.
- **The compose file travels with the code**: change
  `deploy/docker-compose.yml` in the same commit; *Pull and redeploy* picks it
  up from `main`. Release from `main` so the compose file and the images
  match.
- **Never change `FIELD_ENCRYPTION_KEY`** — stored AI / Google keys become
  unreadable.
- **API types**: after changing the backend API, regenerate
  `frontend/src/api/schema.ts` (docs/dev.md) and commit it.
- **Tag only a green CI.** The release runs the tests again and builds
  nothing when they fail.

## Backups and restore

Every night at 03:17 (`TZ`) the backup container writes
`home-<date>.tar.gpg` — the database and the uploaded files, encrypted with
`BACKUP_PASSPHRASE` — into `BACKUP_HOST_DIR`, keeping `BACKUP_KEEP_DAYS` (30).

**Restore** (e.g. after a bad update, or onto a new NAS with the same
secrets):

1. Portainer → Containers: **stop** `backend`, `worker`, `beat` and `web`.
2. `home-dashboard-backup-1` → *Console* → `restore` lists the backups;
   `restore /backups/home-<date>.tar.gpg` → type `YES`. The database and the
   uploaded files are replaced with the backup's.
3. **Start** `backend` (it migrates an older backup up to the running
   version), then `worker`, `beat`, `web`.

Try a restore once after the first setup (e.g. right after adding the family),
so you know it works before you need it.
