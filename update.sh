#!/usr/bin/env bash
#
# Deploy / update BeastMailer.
#
#   bash update.sh
#
# Idempotent: safe to run on a fresh server or over a running stack.
set -euo pipefail

cd "$(dirname "$0")"

bold() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\033[31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

# --- Preflight ------------------------------------------------------------
# Everything is validated before we touch the running stack, so a bad .env
# aborts the deploy instead of half-applying it.

command -v docker >/dev/null 2>&1 || fail "docker is not installed."

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  fail "docker compose is not available. Install the Docker Compose plugin."
fi

if [ ! -f .env ]; then
  cp .env.example .env
  fail ".env did not exist — created it from .env.example. Fill it in, then re-run."
fi

# shellcheck disable=SC1091
set -a; . ./.env; set +a

for var in POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD DATABASE_URL \
           DJANGO_SECRET_KEY DJANGO_ALLOWED_HOSTS MAIL_ENCRYPTION_KEY; do
  value="${!var:-}"
  [ -n "$value" ] || fail "$var is empty in .env"
  case "$value" in
    change-me*) fail "$var still holds a placeholder value in .env" ;;
  esac
done

# Inside a container, localhost is the container itself — not the database.
case "$DATABASE_URL" in
  *@db:*) ;;
  *) fail "DATABASE_URL must point at host 'db' (the compose service), not localhost." ;;
esac

[ "${DJANGO_DEBUG:-0}" = "0" ] || fail "DJANGO_DEBUG must be 0 in production."

# --- Pull latest code -----------------------------------------------------
if [ -d .git ]; then
  bold "Pulling latest code"
  git pull --ff-only
else
  bold "Not a git repository — deploying the working tree as-is"
fi

# --- Build ----------------------------------------------------------------
bold "Building images"
$DC build

# --- Database -------------------------------------------------------------
# Start Postgres alone and wait for its healthcheck, so migrations never race it.
bold "Starting database"
$DC up -d db

printf 'waiting for postgres'
for _ in $(seq 1 60); do
  if $DC exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    printf ' ready\n'; break
  fi
  printf '.'; sleep 2
done
$DC exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1 \
  || fail "postgres did not become ready in time."

bold "Applying migrations"
$DC run --rm --no-deps backend python manage.py migrate --noinput

bold "Collecting static files"
$DC run --rm --no-deps backend python manage.py collectstatic --noinput

# --- Start everything -----------------------------------------------------
bold "Starting services"
$DC up -d --remove-orphans

bold "Cleaning up old images"
docker image prune -f >/dev/null

# --- Report ---------------------------------------------------------------
bold "Status"
$DC ps

port="${HTTP_PORT:-80}"
printf '\n'
if curl -fsS -o /dev/null "http://localhost:${port}/" 2>/dev/null; then
  printf '\033[32m✓ App responding on port %s\033[0m\n' "$port"
else
  printf '\033[33m! App not responding yet on port %s — check: %s logs -f\033[0m\n' "$port" "$DC"
fi

cat <<EOF

Deployed. Useful commands:
  $DC logs -f engine     # mail poller / reply sender
  $DC logs -f backend    # API
  $DC run --rm backend python manage.py createsuperuser
EOF
