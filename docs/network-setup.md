# Network setup (QNAP + Nginx Proxy Manager + AdGuard + Cloudflare)

Target: reach `https://dashboard.<your-domain>` from the LAN and over your
existing VPN, with a browser-trusted certificate, without exposing anything
to the public internet.

## 1. Pick the hostname

Use a subdomain of a domain you own and have on Cloudflare, e.g.
`dashboard.szymanowski.dev`. **Do not create a public `A` record for it** —
the cert is issued via DNS-01 (TXT record on `_acme-challenge.dashboard`),
so there's no need to point an `A` record at anything public.

If you want the LetsEncrypt *staging* endpoint first for testing, NPM has
a toggle in the SSL dialog.

## 2. Cloudflare → NPM API token

In the Cloudflare dashboard → *My Profile* → *API Tokens* → *Create Token*,
template "Edit zone DNS", restricted to the domain's zone. Save the token —
NPM asks for it in step 4.

## 3. Nginx Proxy Manager proxy host

Add a new proxy host:

- **Domain names:** `dashboard.<your-domain>`
- **Scheme:** `http`
- **Forward Hostname / IP:** the NAS LAN IP (or the compose network alias if
  NPM runs on the same Docker network as this stack)
- **Forward Port:** `8080` (the port the `web` container publishes)
- **Block Common Exploits:** on
- **Websockets Support:** off (we use SSE)

**Custom Nginx Configuration** (so SSE streams through):

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 300s;
proxy_send_timeout 300s;
client_max_body_size 25m;
```

## 4. SSL tab

- *Request a new SSL Certificate*
- *DNS Challenge*: on, provider **Cloudflare**, paste the API token
- *Force SSL*, *HTTP/2 Support*, *HSTS Enabled*: on
- *Email Address for Let's Encrypt*: your email
- Save — NPM solves the DNS-01 challenge and issues a real LE cert.

> **Why DNS-01 and not Cloudflare Origin CA**: Origin CA certs are only
> trusted by Cloudflare itself, which we never pass through. Phones hitting
> the NAS directly would show a warning. LE DNS-01 produces a browser-
> trusted cert without opening any inbound port.

## 5. Access List (belt & braces)

Create an Access List limited to your LAN and VPN subnets (e.g.
`192.168.1.0/24`, `100.64.0.0/10` for your WireGuard pool), then attach it
to the proxy host. Even if the hostname leaks, nothing outside those
subnets can reach it.

## 6. AdGuard DNS rewrite

Settings → DNS rewrites → add `dashboard.<your-domain> → <NAS LAN IP>`.
Every device using AdGuard as DNS now resolves the hostname locally.

(If you use the VPN's DNS instead, add the same rewrite there.)

## 7. Google OAuth client (for calendar)

Google Cloud Console → *APIs & Services* → *Credentials* → *Create credentials
→ OAuth client ID* → *Web application*:

- **Authorized JavaScript origins:** `https://dashboard.<your-domain>`
- **Authorized redirect URIs:** `https://dashboard.<your-domain>/api/gcal/callback`

OAuth consent screen: *External* → *Publish app* (keep it in production,
not Testing, otherwise refresh tokens expire after 7 days). Scopes:
`.../auth/calendar` + `.../auth/userinfo.email`.

Copy the client ID / secret into `.env`.

## 8. VAPID keys (web push)

Once, before starting the stack:

```powershell
docker compose run --rm backend python -c "from py_vapid import Vapid01; v=Vapid01(); v.generate_keys(); print(v.private_pem().decode()); print(v.public_pem().decode())"
```

Paste the resulting keys into `.env` (`VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`).
Set `VAPID_ADMIN_EMAIL` to your email.

## 9. Backup target

`docker-compose.yml` mounts `${BACKUP_HOST_DIR:-./data/backups}` into the
`backup` container. Point that variable at a mounted QNAP share (encrypted
volume recommended), and set up HBS3 to copy the whole directory off-device
nightly. Files are already encrypted with `BACKUP_PASSPHRASE`.
