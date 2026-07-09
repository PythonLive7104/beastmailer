# Deploying BeastMailer (generalautoreply.info)

Everything runs in Docker on a single server. Postgres is a container on the same
box with **no published port**, so it is reachable only from the compose network —
never from the internet.

```
                    :80
  internet ──▶ [ web ]  nginx: serves the React SPA,
                  │      proxies /api /admin /r/, serves /static /media
                  ▼
              [ backend ]  gunicorn (Django API)
              [ engine  ]  manage.py run_engine  ← polls mail, sends replies
                  │
                  ▼
              [ db ]  postgres:16   (volume: pgdata)
```

## Services

| Service   | What it does                                            |
| --------- | ------------------------------------------------------- |
| `db`      | Postgres 16. Data in the `pgdata` volume.               |
| `backend` | The REST API, served by gunicorn.                       |
| `engine`  | Polls mailboxes, sends due auto-replies. **Required.**  |
| `web`     | nginx: the SPA + reverse proxy. The only exposed port.  |

`engine` is a separate process from `backend` by design. If it isn't running, the API
still works but **no mail is ever polled or sent**.

## First deploy

```bash
git clone <your-repo> && cd client_sender

cp .env.example .env
nano .env          # fill in every value — see below

bash update.sh
```

`update.sh` is idempotent: run it for the first deploy and for every update after.
It validates `.env`, builds images, waits for Postgres to be healthy, runs migrations
and `collectstatic`, starts everything, and prunes old images. If `.env` is missing or
still holds placeholder values, it aborts **before** touching the running stack.

Then create your login:

```bash
docker compose run --rm backend python manage.py createsuperuser
```

## Filling in `.env`

The important ones:

- `DJANGO_ALLOWED_HOSTS=generalautoreply.info,www.generalautoreply.info`
- `CSRF_TRUSTED_ORIGINS=https://generalautoreply.info,https://www.generalautoreply.info`
- `DATABASE_URL` — host **must** be `db`, the compose service name. Inside a container
  `localhost` means that container itself, not the database. `update.sh` refuses to
  deploy if you get this wrong.
- If the Postgres password contains `@ : / #`, percent-encode it in `DATABASE_URL`
  (`@` → `%40`). The generated password avoids those characters.

⚠ **`MAIL_ENCRYPTION_KEY` must be the exact value your existing data was encrypted
with.** It is the Fernet key protecting every mailbox and proxy password. A new key
makes all stored credentials permanently unreadable. It has already been carried over
from `backend/.env` into `.env`.

## Updating

```bash
git pull        # optional; update.sh does this too when in a git repo
bash update.sh
```

## HTTPS

`web` serves plain HTTP on port 80. Two options:

**Caddy or an existing nginx on the host** — set `HTTP_PORT=8080` in `.env` so the
container stops competing for port 80, then reverse-proxy `generalautoreply.info` to
`127.0.0.1:8080`. Forward `X-Forwarded-Proto: https`; Django already trusts it via
`SECURE_PROXY_SSL_HEADER`.

**Certbot directly on the `web` container** — mount certs and add a `listen 443 ssl`
block to `frontend/nginx.conf`.

Until TLS is in front, admin logins over plain HTTP will work but sessions are not
encrypted. Do not run this publicly without HTTPS.

## Moving existing SQLite data across

Only if you have real data in `backend/db.sqlite3` worth keeping:

```bash
# On your machine, with backend/.env DATABASE_URL empty (so it reads SQLite):
cd backend
venv/bin/python manage.py dumpdata --natural-foreign --natural-primary \
  -e contenttypes -e auth.Permission -e sessions > ../dump.json
cd ..

# Then load it into the containerised Postgres:
docker compose up -d db
docker compose run --rm backend python manage.py migrate
docker compose run --rm -v "$PWD/dump.json:/app/dump.json" backend \
  python manage.py loaddata /app/dump.json
```

Encrypted password fields survive untouched, provided `MAIL_ENCRYPTION_KEY` matches.

## Operating

```bash
docker compose ps
docker compose logs -f engine       # mail poller / reply sender
docker compose logs -f backend      # API
docker compose restart engine
docker compose down                 # stop (volumes, and so data, are kept)
```

### Backups

```bash
docker compose exec -T db pg_dump -U beastmailer beastmailer | gzip > backup-$(date +%F).sql.gz
```

Restore:

```bash
gunzip -c backup-2026-07-09.sql.gz | docker compose exec -T db psql -U beastmailer -d beastmailer
```

## Running without Docker (local dev)

Leave `DATABASE_URL` empty in `backend/.env` and the app falls back to the bundled
`db.sqlite3` file. The root `.env` is only read by docker compose.
